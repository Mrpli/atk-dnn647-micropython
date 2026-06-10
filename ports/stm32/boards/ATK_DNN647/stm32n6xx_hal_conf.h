/* This file is part of the MicroPython project, http://micropython.org/
 * The MIT License (MIT)
 * Copyright (c) 2019 Damien P. George
 */
#ifndef MICROPY_INCLUDED_STM32N6XX_HAL_CONF_H
#define MICROPY_INCLUDED_STM32N6XX_HAL_CONF_H

// Oscillator values in Hz
#define HSE_VALUE (48000000)
#define LSE_VALUE (32768)

// Oscillator timeouts in ms
#define HSE_STARTUP_TIMEOUT (100)
#define LSE_STARTUP_TIMEOUT (5000)

// STM32N647xx does not include the MCE (Memory Cipher Engine) peripheral.
// Define the missing RCC register bits as reserved (0) so the HAL driver's
// ll_bus.h can compile its LL_AHB5_GRP1_PERIPH_ALL macro.
#ifndef RCC_AHB5ENR_MCE1EN
#define RCC_AHB5ENR_MCE1EN                     (0U)
#define RCC_AHB5ENR_MCE2EN                     (0U)
#define RCC_AHB5ENR_MCE3EN                     (0U)
#define RCC_AHB5ENR_MCE4EN                     (0U)
#define RCC_AHB5LPENR_MCE1LPEN                 (0U)
#define RCC_AHB5LPENR_MCE2LPEN                 (0U)
#define RCC_AHB5LPENR_MCE3LPEN                 (0U)
#define RCC_AHB5LPENR_MCE4LPEN                 (0U)
#define RCC_AHB5ENSR_MCE1ENS                   (0U)
#define RCC_AHB5ENSR_MCE2ENS                   (0U)
#define RCC_AHB5ENSR_MCE3ENS                   (0U)
#define RCC_AHB5ENSR_MCE4ENS                   (0U)
#define RCC_AHB5LPENSR_MCE1LPENS               (0U)
#define RCC_AHB5LPENSR_MCE2LPENS               (0U)
#define RCC_AHB5LPENSR_MCE3LPENS               (0U)
#define RCC_AHB5LPENSR_MCE4LPENS               (0U)
#endif

#include "boards/stm32n6xx_hal_conf_base.h"

#endif // MICROPY_INCLUDED_STM32N6XX_HAL_CONF_H
