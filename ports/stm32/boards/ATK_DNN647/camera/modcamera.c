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
/* DCMIPP and CSI IRQ handlers — override the weak Default_Handler     */
/* in the startup file.  Without these, any DCMIPP/CSI interrupt       */
/* jumps to Default_Handler (infinite loop), freezing the system.      */
/* ------------------------------------------------------------------ */
extern DCMIPP_HandleTypeDef hcamera_dcmipp;

void DCMIPP_IRQHandler(void) {
    HAL_DCMIPP_IRQHandler(&hcamera_dcmipp);
}

void CSI_IRQHandler(void) {
    HAL_DCMIPP_CSI_IRQHandler(&hcamera_dcmipp);
}

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
        LL_RCC_PLL2_SetP1(1);
        LL_RCC_PLL2_SetP2(1);
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
        LL_RCC_PLL4_SetP1(1);
        LL_RCC_PLL4_SetP2(1);
        LL_RCC_PLL4P_Enable();
        LL_RCC_PLL4_Enable();
        while (!LL_RCC_PLL4_IsReady()) {
        }
    }

    /* --- IC17 (DCMIPP): PLL2 P1 ÷ 4 = 1200 / 4 = 300 MHz --- */
    MODIFY_REG(RCC->IC17CFGR,
               RCC_IC17CFGR_IC17SEL | RCC_IC17CFGR_IC17INT,
               RCC_ICCLKSOURCE_PLL2 | ((4U - 1U) << RCC_IC17CFGR_IC17INT_Pos));
    LL_RCC_IC17_Enable();

    /* --- IC18 (CSI): PLL4 P1 ÷ 20 = 400 / 20 = 20 MHz --- */
    MODIFY_REG(RCC->IC18CFGR,
               RCC_IC18CFGR_IC18SEL | RCC_IC18CFGR_IC18INT,
               RCC_ICCLKSOURCE_PLL4 | ((20U - 1U) << RCC_IC18CFGR_IC18INT_Pos));
    LL_RCC_IC18_Enable();

    /* --- Route DCMIPP kernel clock to IC17 (CCIPR1) --- */
    MODIFY_REG(RCC->CCIPR1, RCC_CCIPR1_DCMIPPSEL, LL_RCC_DCMIPP_CLKSOURCE_IC17);

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
    if (buf == NULL) {
        mp_raise_msg_varg(&mp_type_MemoryError,
            MP_ERROR_TEXT("cannot allocate %u bytes for frame buffer"), buf_size);
    }

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

    /* Return as bytearray — avoids extra copy that doubles memory usage */
    mp_obj_t result = mp_obj_new_bytearray_by_ref(buf_size, buf);
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
/* camera.clock_test() — dump PLL and IC registers for diagnostics     */
/* ------------------------------------------------------------------ */
static mp_obj_t camera_clock_test(void) {
    static const char *src_name[] = {"HSI(64M)", "MSI(4/16M)", "HSE(48M)", "I2S_CKIN", "", "", "", ""};
    uint32_t cfgr1, sel, divm, divn, vco;

    printf("\r\n========== PLL Register Dump ==========\r\n");

    for (int i = 1; i <= 4; i++) {
        switch (i) {
            case 1: cfgr1 = RCC->PLL1CFGR1; break;
            case 2: cfgr1 = RCC->PLL2CFGR1; break;
            case 3: cfgr1 = RCC->PLL3CFGR1; break;
            case 4: cfgr1 = RCC->PLL4CFGR1; break;
        }
        /* PLLxSEL: bits [30:28], PLLxDIVM: bits [25:20], PLLxDIVN: bits [19:8] */
        sel  = (cfgr1 >> 28) & 0x7;
        divm = (cfgr1 >> 20) & 0x3F;
        divn = (cfgr1 >> 8)  & 0xFFF;

        uint32_t src_freq;
        switch (sel) {
            case 0:  src_freq = (uint32_t)HSI_VALUE; break;
            case 1:  src_freq = 4000000UL; break;
            case 2:  src_freq = (uint32_t)HSE_VALUE; break;
            default: src_freq = 0; break;
        }

        if (divm > 0) {
            vco = src_freq / divm * divn;
            printf("PLL%d: src=%-10s M=%2lu N=%3lu  VCO=%lu Hz  raw=0x%08lX\r\n",
                   i, src_name[sel], divm, divn, vco, cfgr1);
        } else {
            printf("PLL%d: M=0 (PLL disabled)  raw=0x%08lX\r\n", i, cfgr1);
        }
    }

    /* PLL VCO for calculating IC output frequencies */
    uint32_t pll_vco[5] = {0};
    for (int i = 1; i <= 4; i++) {
        uint32_t r;
        switch (i) {
            case 1: r = RCC->PLL1CFGR1; break;
            case 2: r = RCC->PLL2CFGR1; break;
            case 3: r = RCC->PLL3CFGR1; break;
            case 4: r = RCC->PLL4CFGR1; break;
        }
        uint32_t s = (r >> 28) & 0x7;
        uint32_t m = (r >> 20) & 0x3F;
        uint32_t n = (r >> 8)  & 0xFFF;
        uint32_t f;
        switch (s) {
            case 0:  f = (uint32_t)HSI_VALUE; break;
            case 1:  f = 4000000UL; break;
            case 2:  f = (uint32_t)HSE_VALUE; break;
            default: f = 0; break;
        }
        if (m > 0) pll_vco[i] = f / m * n;
    }

    /* IC dividers — print only the ones we care about, direct reads */
    printf("\r\n--- IC dividers ---\r\n");
    #define DUMP_IC(n, label) do { \
        uint32_t _val = RCC->IC##n##CFGR; \
        uint32_t _div = ((_val >> 16) & 0xFF) + 1; \
        uint32_t _src = (_val >> 28) & 0x3; \
        uint32_t _freq = (pll_vco[_src + 1] > 0) ? pll_vco[_src + 1] / _div : 0; \
        printf("IC%-2d (%-8s) div=%2lu  %8lu Hz  src=PLL%lu  raw=0x%08lX\r\n", \
               n, label, _div, _freq, _src + 1, _val); \
    } while (0)

    DUMP_IC(1,  "CPU");
    DUMP_IC(2,  "HCLK");
    DUMP_IC(4,  "XSPI1");
    DUMP_IC(12, "ETH");
    DUMP_IC(14, "SlowPer");
    DUMP_IC(17, "DCMIPP");
    DUMP_IC(18, "CSI");

    #undef DUMP_IC

    /* PLL2/PLL4 ready status */
    printf("PLL2 ready=%lu  PLL4 ready=%lu\r\n",
           LL_RCC_PLL2_IsReady(), LL_RCC_PLL4_IsReady());

    printf("========================================\r\n\r\n");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_clock_test_obj, camera_clock_test);

/* ------------------------------------------------------------------ */
/* Module table                                                        */
/* ------------------------------------------------------------------ */
static const mp_rom_map_elem_t camera_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),    MP_ROM_QSTR(MP_QSTR_camera)         },
    { MP_ROM_QSTR(MP_QSTR_init),        MP_ROM_PTR(&camera_init_obj)        },
    { MP_ROM_QSTR(MP_QSTR_capture),     MP_ROM_PTR(&camera_capture_obj)     },
    { MP_ROM_QSTR(MP_QSTR_run),         MP_ROM_PTR(&camera_run_obj)         },
    { MP_ROM_QSTR(MP_QSTR_deinit),      MP_ROM_PTR(&camera_deinit_obj)      },
    { MP_ROM_QSTR(MP_QSTR_clock_test),  MP_ROM_PTR(&camera_clock_test_obj)  },
};
static MP_DEFINE_CONST_DICT(camera_module_globals, camera_module_globals_table);

const mp_obj_module_t mp_module_camera = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&camera_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_camera, mp_module_camera);
