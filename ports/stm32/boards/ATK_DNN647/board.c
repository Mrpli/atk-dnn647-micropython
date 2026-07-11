/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2024-2025 Damien P. George
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "py/mphal.h"
#include "boardctrl.h"
#include "xspi.h"

// Values for OTP fuses for VDDIO3, to select low voltage mode (<2.5V).
// See RM0486, Section 5, Table 18.
#define BSEC_HW_CONFIG_ID       (124U)
#define BSEC_HWS_HSLV_VDDIO3    (1U << 15)

static void board_config_vdd(void) {
    // TODO: move some of the below code to a common location for all N6 boards?

    // Enable PWR, BSEC and SYSCFG clocks.
    LL_AHB4_GRP1_EnableClock(LL_AHB4_GRP1_PERIPH_PWR);
    LL_APB4_GRP2_EnableClock(LL_APB4_GRP2_PERIPH_BSEC);
    LL_APB4_GRP2_EnableClock(LL_APB4_GRP2_PERIPH_SYSCFG);

    // Program high speed IO optimization fuses if they aren't already set.
    uint32_t fuse;
    BSEC_HandleTypeDef hbsec = { .Instance = BSEC };
    const uint32_t mask = BSEC_HWS_HSLV_VDDIO3;
    if (HAL_BSEC_OTP_Read(&hbsec, BSEC_HW_CONFIG_ID, &fuse) != HAL_OK) {
        fuse = 0;
    } else if ((fuse & mask) != mask) {
        // Program the fuse, and read back the set value.
        if (HAL_BSEC_OTP_Program(&hbsec, BSEC_HW_CONFIG_ID, fuse | mask, HAL_BSEC_NORMAL_PROG) != HAL_OK) {
            fuse = 0;
        } else if (HAL_BSEC_OTP_Read(&hbsec, BSEC_HW_CONFIG_ID, &fuse) != HAL_OK) {
            fuse = 0;
        }
    }

    // Enable Vdd ADC, needed for the ADC to work.
    LL_PWR_EnableVddADC();

    // Configure VDDIO2.
    LL_PWR_EnableVddIO2();
    LL_PWR_SetVddIO2VoltageRange(LL_PWR_VDDIO_VOLTAGE_RANGE_3V3);
    SYSCFG->VDDIO2CCCR |= SYSCFG_VDDIO2CCCR_EN; // enable IO compensation

    // Configure VDDIO3.  Only enable 1.8V mode if the fuse is set.
    LL_PWR_EnableVddIO3();
    if (fuse & BSEC_HWS_HSLV_VDDIO3) {
        LL_PWR_SetVddIO3VoltageRange(LL_PWR_VDDIO_VOLTAGE_RANGE_1V8);
    }
    SYSCFG->VDDIO3CCCR |= SYSCFG_VDDIO3CCCR_EN; // enable IO compensation

    // Configure VDDIO4.
    LL_PWR_EnableVddIO4();
    LL_PWR_SetVddIO4VoltageRange(LL_PWR_VDDIO_VOLTAGE_RANGE_3V3);
    SYSCFG->VDDIO4CCCR |= SYSCFG_VDDIO4CCCR_EN; // enable IO compensation

    // Enable VDD for ADC and USB.
    LL_PWR_EnableVddADC();
    LL_PWR_EnableVddUSB();
}

void mboot_board_early_init(void) {
    board_config_vdd();

    /* Match CubeIDE FSBL: configure SMPS supply + voltage scaling */
    HAL_PWREx_ConfigSupply(PWR_SMPS_SUPPLY);
    HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE0);

    xspi_init();

    /*
     * Pre-configure PLL2 / PLL4 and IC17 / IC18 for DCMIPP + CSI.
     * In the CubeIDE project these are set up in the FSBL; mboot is
     * the MicroPython equivalent.  Raw register writes with DSB
     * barriers — the STM32N6 RIF may silently drop writes made
     * through LL / HAL helpers on locked peripherals.
     *
     * PLL2: HSE 48 MHz, /2, *50, P1=1 → VCO = 1200 MHz
     * IC17: PLL2 / 3 = 400 MHz  (DCMIPP kernel)
     * PLL4: HSE 48 MHz, /3, *25, P1=1 → VCO = 400 MHz
     * IC18: PLL4 / 20 = 20 MHz   (CSI PHY)
     */
    if (!(RCC->SR & RCC_SR_PLL2RDY)) {
        RCC->PLL2CFGR1 = (2U << RCC_PLL2CFGR1_PLL2SEL_Pos)
                       | (2U << RCC_PLL2CFGR1_PLL2DIVM_Pos)
                       | (50U << RCC_PLL2CFGR1_PLL2DIVN_Pos);
        RCC->PLL2CFGR2 = 0;
        RCC->PLL2CFGR3 = (1U << RCC_PLL2CFGR3_PLL2PDIV1_Pos)
                       | (1U << RCC_PLL2CFGR3_PLL2PDIV2_Pos)
                       | RCC_PLL2CFGR3_PLL2PDIVEN;
        __DSB();
        RCC->CSR |= RCC_CSR_PLL2ONS;
        __DSB();
        while (!(RCC->SR & RCC_SR_PLL2RDY)) { }
    }

    if (!(RCC->SR & RCC_SR_PLL4RDY)) {
        RCC->PLL4CFGR1 = (2U << RCC_PLL4CFGR1_PLL4SEL_Pos)
                       | (3U << RCC_PLL4CFGR1_PLL4DIVM_Pos)
                       | (25U << RCC_PLL4CFGR1_PLL4DIVN_Pos);
        RCC->PLL4CFGR2 = 0;
        RCC->PLL4CFGR3 = (1U << RCC_PLL4CFGR3_PLL4PDIV1_Pos)
                       | (1U << RCC_PLL4CFGR3_PLL4PDIV2_Pos)
                       | RCC_PLL4CFGR3_PLL4PDIVEN;
        __DSB();
        RCC->CSR |= RCC_CSR_PLL4ONS;
        __DSB();
        while (!(RCC->SR & RCC_SR_PLL4RDY)) { }
    }

    /* IC17: DCMIPP kernel clock = PLL2 / 3 = 400 MHz */
    MODIFY_REG(RCC->IC17CFGR,
               RCC_IC17CFGR_IC17SEL | RCC_IC17CFGR_IC17INT,
               RCC_ICCLKSOURCE_PLL2 | ((3U - 1U) << RCC_IC17CFGR_IC17INT_Pos));
    LL_RCC_IC17_Enable();

    /* IC18: CSI PHY clock = PLL4 / 20 = 20 MHz */
    MODIFY_REG(RCC->IC18CFGR,
               RCC_IC18CFGR_IC18SEL | RCC_IC18CFGR_IC18INT,
               RCC_ICCLKSOURCE_PLL4 | ((20U - 1U) << RCC_IC18CFGR_IC18INT_Pos));
    LL_RCC_IC18_Enable();

    /* Route DCMIPP kernel clock to IC17 */
    MODIFY_REG(RCC->CCIPR1, RCC_CCIPR1_DCMIPPSEL, LL_RCC_DCMIPP_CLKSOURCE_IC17);

    __DSB();
    __ISB();
}

void board_early_init(void) {
    #if !MICROPY_HW_RUNS_FROM_EXT_FLASH
    // Firmware runs directly from SRAM, so configure VDD and enable XSPI flash.
    board_config_vdd();
    xspi_init();
    #else
    /*
     * When running from XSPI flash (USE_MBOOT=1), mboot already configured
     * VDDIO.  Re-enable the I/O supplies here in case the main firmware's
     * startup path reset or reconfigured them.  This is critical for the
     * camera control pins on GPIOG (VDDIO4, 3.3V).
     */
    LL_AHB4_GRP1_EnableClock(LL_AHB4_GRP1_PERIPH_PWR);
    LL_PWR_EnableVddIO4();
    LL_PWR_EnableVddIO3();
    LL_PWR_EnableVddIO2();
    #endif

    /*
     * Pre-configure PLL2 / PLL4 and IC17 / IC18 for DCMIPP + CSI.
     * These clocks are needed by the MIPI camera interface and must be
     * ready before HAL_DCMIPP_Init is called (it selects IC17←PLL2
     * and IC18←PLL4 via PeriphCLKConfig).
     *
     * This matches the CubeIDE FSBL approach — PLLs are set up at boot,
     * not lazily in the camera driver.  Raw register writes with DSB
     * barriers are used because the STM32N6 RIF may silently reject
     * writes made through LL / HAL helper macros.
     *
     * Clock targets:
     *   PLL2: HSE 48MHz, /2, *50, P1=1 → VCO = 1200 MHz
     *   IC17: PLL2 / 3 = 400 MHz (DCMIPP kernel, max 400 MHz)
     *   PLL4: HSE 48MHz, /3, *25, P1=1 → VCO = 400 MHz
     *   IC18: PLL4 / 20 = 20 MHz (CSI PHY)
     */
    if (!(RCC->SR & RCC_SR_PLL2RDY)) {
        RCC->PLL2CFGR1 = (2U << RCC_PLL2CFGR1_PLL2SEL_Pos)
                       | (2U << RCC_PLL2CFGR1_PLL2DIVM_Pos)
                       | (50U << RCC_PLL2CFGR1_PLL2DIVN_Pos);
        RCC->PLL2CFGR2 = 0;
        RCC->PLL2CFGR3 = (1U << RCC_PLL2CFGR3_PLL2PDIV1_Pos)
                       | (1U << RCC_PLL2CFGR3_PLL2PDIV2_Pos)
                       | RCC_PLL2CFGR3_PLL2PDIVEN;
        __DSB();
        RCC->CSR |= RCC_CSR_PLL2ONS;  /* enable PLL2 */
        __DSB();
        while (!(RCC->SR & RCC_SR_PLL2RDY)) { }
    }

    if (!(RCC->SR & RCC_SR_PLL4RDY)) {
        RCC->PLL4CFGR1 = (2U << RCC_PLL4CFGR1_PLL4SEL_Pos)
                       | (3U << RCC_PLL4CFGR1_PLL4DIVM_Pos)
                       | (25U << RCC_PLL4CFGR1_PLL4DIVN_Pos);
        RCC->PLL4CFGR2 = 0;
        RCC->PLL4CFGR3 = (1U << RCC_PLL4CFGR3_PLL4PDIV1_Pos)
                       | (1U << RCC_PLL4CFGR3_PLL4PDIV2_Pos)
                       | RCC_PLL4CFGR3_PLL4PDIVEN;
        __DSB();
        RCC->CSR |= RCC_CSR_PLL4ONS;  /* enable PLL4 */
        __DSB();
        while (!(RCC->SR & RCC_SR_PLL4RDY)) { }
    }

    /* IC17: DCMIPP kernel clock = PLL2 / 3 = 400 MHz */
    MODIFY_REG(RCC->IC17CFGR,
               RCC_IC17CFGR_IC17SEL | RCC_IC17CFGR_IC17INT,
               RCC_ICCLKSOURCE_PLL2 | ((3U - 1U) << RCC_IC17CFGR_IC17INT_Pos));
    LL_RCC_IC17_Enable();

    /* IC18: CSI PHY clock = PLL4 / 20 = 20 MHz */
    MODIFY_REG(RCC->IC18CFGR,
               RCC_IC18CFGR_IC18SEL | RCC_IC18CFGR_IC18INT,
               RCC_ICCLKSOURCE_PLL4 | ((20U - 1U) << RCC_IC18CFGR_IC18INT_Pos));
    LL_RCC_IC18_Enable();

    /* Route DCMIPP kernel clock to IC17 */
    MODIFY_REG(RCC->CCIPR1, RCC_CCIPR1_DCMIPPSEL, LL_RCC_DCMIPP_CLKSOURCE_IC17);

    __DSB();
    __ISB();
}

void board_leave_standby(void) {
    // TODO: move some of the below code to a common location for all N6 boards?

    // Enable PWR, BSEC and SYSCFG clocks.
    LL_AHB4_GRP1_EnableClock(LL_AHB4_GRP1_PERIPH_PWR);
    LL_APB4_GRP2_EnableClock(LL_APB4_GRP2_PERIPH_BSEC);
    LL_APB4_GRP2_EnableClock(LL_APB4_GRP2_PERIPH_SYSCFG);

    // Configure VDDIO2.
    LL_PWR_EnableVddIO2();
    LL_PWR_SetVddIO2VoltageRange(LL_PWR_VDDIO_VOLTAGE_RANGE_3V3);
    SYSCFG->VDDIO2CCCR |= SYSCFG_VDDIO2CCCR_EN; // enable IO compensation

    // Configure VDDIO3 (1.8V mode selection is retained).
    LL_PWR_EnableVddIO3();
    SYSCFG->VDDIO3CCCR |= SYSCFG_VDDIO3CCCR_EN; // enable IO compensation

    // Configure VDDIO4.
    LL_PWR_EnableVddIO4();
    LL_PWR_SetVddIO4VoltageRange(LL_PWR_VDDIO_VOLTAGE_RANGE_3V3);
    SYSCFG->VDDIO4CCCR |= SYSCFG_VDDIO4CCCR_EN; // enable IO compensation

    // Enable VDD for ADC and USB.
    LL_PWR_EnableVddADC();
    LL_PWR_EnableVddUSB();
}
