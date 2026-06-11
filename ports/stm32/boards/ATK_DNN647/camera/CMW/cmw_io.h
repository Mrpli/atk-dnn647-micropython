/*
 * Board IO adapter for STM32_MW_CAMERA on ATK-DNN647.
 *
 * Pin assignments from ATK-DNN647 schematic:
 *   CSI_CAM_PWDN (camera power enable, active-high) -> PG6
 *   CSI_CAM_RST  (camera reset, active-low)         -> PG4
 *   I2C2_SCL                                        -> PD14 (AF4)
 *   I2C2_SDA                                        -> PD4  (AF4)
 *   I2C2 timing = 0x10707DBC  @ CLKP = 100 MHz, 100 kHz
 *   IMX335 I2C address = 0x34 (ALIENTEK module)
 */

#ifndef CMW_IO_H
#define CMW_IO_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32n6xx_hal.h"
#include <stdio.h>

/* IMX335 I2C address
 * 8-bit write addresses: 0x34 or 0x36 depending on SLASEL strap
 * ALIENTEK IMX335 module uses 0x34 */
#define CAMERA_IMX335_ADDRESS  0x34U

/* ---- Camera control GPIO ---- */
/* CSI_CAM_PWDN: PG6  active-high enable */
#define EN_CAM_PORT   GPIOG
#define EN_CAM_PIN    GPIO_PIN_6
#define EN_CAM_GPIO_CLK_ENABLE()   __HAL_RCC_GPIOG_CLK_ENABLE()

/* CSI_CAM_RST: PG4  active-low reset */
#define NRST_CAM_PORT   GPIOG
#define NRST_CAM_PIN    GPIO_PIN_4
#define NRST_CAM_GPIO_CLK_ENABLE()  __HAL_RCC_GPIOG_CLK_ENABLE()

/* VDDIO for GPIOG is VDDIO4 (3.3V) — already enabled by board_early_init(). */
#define EN_CAM_GPIO_ENABLE_VDDIO()   do { } while (0)
#define NRST_CAM_GPIO_ENABLE_VDDIO() do { } while (0)

/* ---- I2C2 handle — defined in modcamera.c ---- */
extern I2C_HandleTypeDef hi2c2_cam;

#define CAMERA_DBG 1

static inline int32_t CMW_IO_I2C_Init(void) {
    if (hi2c2_cam.Instance != NULL) {
        if (CAMERA_DBG) {
            printf("[cam] I2C skip (already init)\r\n");
        }
        return 0; /* already initialised */
    }
    if (CAMERA_DBG) {
        printf("[cam] I2C Init: GPIOD PD14/PD4 AF4...\r\n");
    }

    /* PD14 = I2C2_SCL (AF4),  PD4 = I2C2_SDA (AF4)  open-drain */
    __HAL_RCC_GPIOD_CLK_ENABLE();
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_14 | GPIO_PIN_4;
    gpio.Mode = GPIO_MODE_AF_OD;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    gpio.Alternate = GPIO_AF4_I2C2;
    HAL_GPIO_Init(GPIOD, &gpio);

    /* I2C2 peripheral clock from CLKP (100 MHz) */
    RCC_PeriphCLKInitTypeDef clk = {0};
    clk.PeriphClockSelection = RCC_PERIPHCLK_I2C2;
    clk.I2c2ClockSelection = RCC_I2C2CLKSOURCE_CLKP;
    if (HAL_RCCEx_PeriphCLKConfig(&clk) != HAL_OK) {
        if (CAMERA_DBG) {
            printf("[cam] I2C Init: CLOCK CONFIG FAILED\r\n");
        }
        return -1;
    }
    __HAL_RCC_I2C2_CLK_ENABLE();

    hi2c2_cam.Instance = I2C2;
    hi2c2_cam.Init.Timing = 0x10707DBC;           /* 100 kHz @ 100 MHz CLKP */
    hi2c2_cam.Init.OwnAddress1 = 0;
    hi2c2_cam.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    hi2c2_cam.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    hi2c2_cam.Init.OwnAddress2 = 0;
    hi2c2_cam.Init.OwnAddress2Masks = I2C_OA2_NOMASK;
    hi2c2_cam.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
    hi2c2_cam.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
    if (HAL_I2C_Init(&hi2c2_cam) != HAL_OK) {
        if (CAMERA_DBG) {
            printf("[cam] I2C Init: HAL_I2C_Init FAILED\r\n");
        }
        return -1;
    }
    HAL_I2CEx_ConfigAnalogFilter(&hi2c2_cam, I2C_ANALOGFILTER_ENABLE);
    HAL_I2CEx_ConfigDigitalFilter(&hi2c2_cam, 0);
    if (CAMERA_DBG) {
        printf("[cam] I2C Init OK\r\n");
    }
    if (CAMERA_DBG) {
        /* Check GPIO state: read EN_CAM(PG6) and NRST_CAM(PG4) */
        int en = (GPIOG->ODR >> 6) & 1;
        int rst = (GPIOG->ODR >> 4) & 1;
        printf("[cam] GPIO: EN_CAM(PG6)=%d NRST_CAM(PG4)=%d (both should be 1)\r\n", en, rst);

        /* Check bus hardware: read SCL/SDA levels */
        GPIO_InitTypeDef g = {0};
        g.Pin = GPIO_PIN_14 | GPIO_PIN_4;
        g.Mode = GPIO_MODE_INPUT;
        g.Pull = GPIO_NOPULL;
        HAL_GPIO_Init(GPIOD, &g);
        int sda = (GPIOD->IDR >> 4) & 1;
        int scl = (GPIOD->IDR >> 14) & 1;
        printf("[cam] I2C bus: SCL=%d SDA=%d (both should be 1)\r\n", scl, sda);
        /* Restore AF */
        g.Mode = GPIO_MODE_AF_OD;
        g.Alternate = GPIO_AF4_I2C2;
        HAL_GPIO_Init(GPIOD, &g);

        /* scan all addresses 1-127 */
        printf("[cam] I2C scan: ");
        for (int a = 1; a < 128; a++) {
            if (HAL_I2C_IsDeviceReady(&hi2c2_cam, (uint16_t)(a << 1), 1, 10) == HAL_OK) {
                printf("0x%02X ", a);
            }
        }
        printf("\r\n");
    }
    return 0;
}

static inline int32_t CMW_IO_I2C_DeInit(void) {
    return 0;
}

static inline int32_t CMW_IO_I2C_WriteReg16(uint16_t dev_addr, uint16_t reg,
    uint8_t *data, uint16_t length) {
    HAL_StatusTypeDef r = HAL_I2C_Mem_Write(&hi2c2_cam, dev_addr, reg,
        I2C_MEMADD_SIZE_16BIT, data, length, 1000U);
    if (CAMERA_DBG) {
        printf("[cam] I2C Write dev=0x%02X reg=0x%04X len=%d => %d\r\n", dev_addr, reg, length, r);
    }
    return (r == HAL_OK) ? 0 : -1;
}

static inline int32_t CMW_IO_I2C_ReadReg16(uint16_t dev_addr, uint16_t reg,
    uint8_t *data, uint16_t length) {
    HAL_StatusTypeDef r = HAL_I2C_Mem_Read(&hi2c2_cam, dev_addr, reg,
        I2C_MEMADD_SIZE_16BIT, data, length, 1000U);
    if (CAMERA_DBG) {
        printf("[cam] I2C Read  dev=0x%02X reg=0x%04X len=%d => %d val=0x%02X\r\n", dev_addr, reg, length, r, (length > 0)?data[0]:0);
    }
    return (r == HAL_OK) ? 0 : -1;
}

static inline int32_t CMW_IO_GetTick(void) {
    return (int32_t)HAL_GetTick();
}

#define CMW_I2C_INIT        CMW_IO_I2C_Init
#define CMW_I2C_DEINIT      CMW_IO_I2C_DeInit
#define CMW_I2C_WRITEREG16  CMW_IO_I2C_WriteReg16
#define CMW_I2C_READREG16   CMW_IO_I2C_ReadReg16
#define BSP_GetTick         CMW_IO_GetTick

#ifdef __cplusplus
}
#endif

#endif /* CMW_IO_H */
