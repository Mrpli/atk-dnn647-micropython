/*
 * MicroPython camera module for ATK-DNN647 with IMX335 sensor.
 *
 * Python API:
 *   import camera
 *   camera.init(width=320, height=240)   # configures Pipe1 output resolution
 *   camera.run()                          # call periodically for ISP AEC/AWB
 *   buf = camera.capture()               # blocking snapshot → bytes (RGB565)
 *   camera.deinit()
 *
 * Hardware (from ATK-DNN647 schematic):
 *   CSI_CAM_PWDN  PG6   I2C2_SCL  PD14 (AF4)
 *   CSI_CAM_RST   PG4   I2C2_SDA  PD4  (AF4)
 *   IMX335 I2C addr = 0x34 (ALIENTEK module)
 */

#include "py/runtime.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "py/mperrno.h"
#include "py/mphal.h"

#include "stm32n6xx_hal.h"
#include "stm32n6xx_hal_rcc_ex.h"
#include "stm32n6xx_ll_rcc.h"

#include "cmw_camera.h"
#include "cmw_io.h"

#include <stdio.h>

/* ------------------------------------------------------------------ */
/* I2C2 handle — referenced by cmw_io.h                               */
/* ------------------------------------------------------------------ */
I2C_HandleTypeDef hi2c2_cam = { .Instance = NULL };

/* ------------------------------------------------------------------ */
/* Frame-ready signalling (set from IRQ context)                       */
/* ------------------------------------------------------------------ */
static volatile int s_frame_ready = 0;

/* ------------------------------------------------------------------ */
/* HAL_DCMIPP_MspInit — overrides the __weak version in cmw_camera.c  */
/* Configures DCMIPP pixel clock (IC17 ← PLL2 ÷ 4 = 300 MHz) and    */
/* CSI clock (IC18 ← PLL4 ÷ 20), enables peripherals, wires IRQs.    */
/* ------------------------------------------------------------------ */
void HAL_DCMIPP_MspInit(DCMIPP_HandleTypeDef *hdcmipp) {
    UNUSED(hdcmipp);

    /* --- Enable PLL2 for DCMIPP (HSE 48MHz, /2=24MHz, *50=1200MHz) -- */
    if (!LL_RCC_PLL2_IsReady()) {
        LL_RCC_PLL2_SetSource(LL_RCC_PLLSOURCE_HSE);
        LL_RCC_PLL2_SetM(2);
        LL_RCC_PLL2_SetN(50);
        LL_RCC_PLL2_SetFRACN(0);
        LL_RCC_PLL2P_Enable();
        LL_RCC_PLL2_Enable();
        while (!LL_RCC_PLL2_IsReady()) {
        }
    }

    /* --- Enable PLL4 for CSI PHY (HSE 48MHz, /3=16MHz, *25=400MHz) -- */
    if (!LL_RCC_PLL4_IsReady()) {
        LL_RCC_PLL4_SetSource(LL_RCC_PLLSOURCE_HSE);
        LL_RCC_PLL4_SetM(3);
        LL_RCC_PLL4_SetN(25);
        LL_RCC_PLL4_SetFRACN(0);
        LL_RCC_PLL4P_Enable();
        LL_RCC_PLL4_Enable();
        while (!LL_RCC_PLL4_IsReady()) {
        }
    }

    /* --- Peripheral clock sources ----------------------------------- */
    RCC_PeriphCLKInitTypeDef clk = {0};
    clk.PeriphClockSelection = RCC_PERIPHCLK_DCMIPP | RCC_PERIPHCLK_CSI;
    clk.DcmippClockSelection = RCC_DCMIPPCLKSOURCE_IC17;
    clk.ICSelection[RCC_IC17].ClockSelection = RCC_ICCLKSOURCE_PLL2;
    clk.ICSelection[RCC_IC17].ClockDivider = 4;     /* PLL2 → 300 MHz */
    clk.ICSelection[RCC_IC18].ClockSelection = RCC_ICCLKSOURCE_PLL4;
    clk.ICSelection[RCC_IC18].ClockDivider = 20;     /* PLL4 → 20 MHz */
    HAL_RCCEx_PeriphCLKConfig(&clk);

    /* --- DCMIPP ---------------------------------------------------- */
    __HAL_RCC_DCMIPP_CLK_ENABLE();
    __HAL_RCC_DCMIPP_CLK_SLEEP_ENABLE();
    __HAL_RCC_DCMIPP_FORCE_RESET();
    __HAL_RCC_DCMIPP_RELEASE_RESET();
    HAL_NVIC_SetPriority(DCMIPP_IRQn, 7, 0);
    HAL_NVIC_EnableIRQ(DCMIPP_IRQn);

    /* --- CSI ------------------------------------------------------- */
    __HAL_RCC_CSI_CLK_ENABLE();
    __HAL_RCC_CSI_CLK_SLEEP_ENABLE();
    __HAL_RCC_CSI_FORCE_RESET();
    __HAL_RCC_CSI_RELEASE_RESET();
    HAL_NVIC_SetPriority(CSI_IRQn, 7, 0);
    HAL_NVIC_EnableIRQ(CSI_IRQn);
}

/* ------------------------------------------------------------------ */
/* CMW_CAMERA_PIPE_FrameEventCallback — overrides __weak in           */
/* cmw_camera.c; called from HAL_DCMIPP_PIPE_FrameEventCallback which */
/* is already non-weak in cmw_camera.c.                               */
/* ------------------------------------------------------------------ */
int CMW_CAMERA_PIPE_FrameEventCallback(uint32_t pipe) {
    if (pipe == DCMIPP_PIPE1) {
        s_frame_ready = 1;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* Pipe1 configuration (shared across init / capture calls)           */
/* ------------------------------------------------------------------ */
static uint32_t s_width = 320;
static uint32_t s_height = 240;
static uint32_t s_pitch = 0;       /* filled by CMW_CAMERA_SetPipeConfig */

/* ------------------------------------------------------------------ */
/* camera.init([width, height])                                        */
/* ------------------------------------------------------------------ */
static mp_obj_t camera_init(size_t n_args, const mp_obj_t *args) {
    if (n_args >= 1) {
        s_width = mp_obj_get_int(args[0]);
    }
    if (n_args >= 2) {
        s_height = mp_obj_get_int(args[1]);
    }

    /* Build CMW init struct for full-sensor 2592×1944 RAW10 stream   */
    CMW_CameraInit_t cfg = {
        .width = 2592,
        .height = 1944,
        .fps = 30,
        .pixel_format = DCMIPP_PIXEL_PACKER_FORMAT_RGB565_1,
        .mirror_flip = CMW_MIRRORFLIP_NONE,
    };
    if (CMW_CAMERA_Init(&cfg) != CMW_ERROR_NONE) {
        printf("[cam] CMW_CAMERA_Init FAILED\r\n");
        mp_raise_OSError(MP_EIO);
    }
    printf("[cam] CMW_CAMERA_Init OK\r\n");

    /* Configure Pipe1: downscale sensor output to requested size     */
    CMW_DCMIPP_Conf_t pipe_conf = {
        .output_width = s_width,
        .output_height = s_height,
        .output_format = DCMIPP_PIXEL_PACKER_FORMAT_RGB565_1,
        .output_bpp = 2,
        .enable_swap = 0,
        .enable_gamma_conversion = -1,  /* ISP controls gamma */
        .mode = CMW_Aspect_ratio_fit,
    };
    if (CMW_CAMERA_SetPipeConfig(DCMIPP_PIPE1, &pipe_conf, &s_pitch) != CMW_ERROR_NONE) {
        mp_raise_OSError(MP_EIO);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_init_obj, 0, 2, camera_init);

/* ------------------------------------------------------------------ */
/* camera.capture() → bytes (RGB565, s_width × s_height × 2 B)       */
/* ------------------------------------------------------------------ */
static mp_obj_t camera_capture(void) {
    /* Allocate frame buffer from MicroPython heap */
    size_t buf_size = (size_t)s_pitch * s_height;
    void *buf = m_malloc(buf_size);

    s_frame_ready = 0;
    if (CMW_CAMERA_Start(DCMIPP_PIPE1, (uint8_t *)buf, CMW_MODE_SNAPSHOT)
        != CMW_ERROR_NONE) {
        m_free(buf);
        mp_raise_OSError(MP_EIO);
    }

    /* Wait up to 2 s for a frame */
    uint32_t t0 = HAL_GetTick();
    while (!s_frame_ready) {
        if ((HAL_GetTick() - t0) > 2000U) {
            m_free(buf);
            mp_raise_OSError(MP_ETIMEDOUT);
        }
        __WFI();
    }

    /* Wrap as immutable bytes and hand back to Python */
    mp_obj_t result = mp_obj_new_bytes((const byte *)buf, buf_size);
    m_free(buf);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_capture_obj, camera_capture);

/* ------------------------------------------------------------------ */
/* camera.run() — process ISP AEC/AWB algorithms; call once per frame */
/* ------------------------------------------------------------------ */
static mp_obj_t camera_run(void) {
    if (CMW_CAMERA_Run() != CMW_ERROR_NONE) {
        mp_raise_OSError(MP_EIO);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_run_obj, camera_run);

/* ------------------------------------------------------------------ */
/* camera.deinit()                                                     */
/* ------------------------------------------------------------------ */
static mp_obj_t camera_deinit(void) {
    CMW_CAMERA_DeInit();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_deinit_obj, camera_deinit);

/* ------------------------------------------------------------------ */
/* Module table                                                        */
/* ------------------------------------------------------------------ */
static const mp_rom_map_elem_t camera_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_camera) },
    { MP_ROM_QSTR(MP_QSTR_init),    MP_ROM_PTR(&camera_init_obj)    },
    { MP_ROM_QSTR(MP_QSTR_capture), MP_ROM_PTR(&camera_capture_obj) },
    { MP_ROM_QSTR(MP_QSTR_run),     MP_ROM_PTR(&camera_run_obj)     },
    { MP_ROM_QSTR(MP_QSTR_deinit),  MP_ROM_PTR(&camera_deinit_obj)  },
};
static MP_DEFINE_CONST_DICT(camera_module_globals, camera_module_globals_table);

const mp_obj_module_t mp_module_camera = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&camera_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_camera, mp_module_camera);
