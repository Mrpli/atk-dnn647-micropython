/*
 * Camera middleware configuration for NUCLEO-N657X0-Q (MicroPython build).
 * Replaces the CubeIDE-generated version that depended on board BSP bus headers.
 */

#ifndef CMW_CAMERA_CONF_H
#define CMW_CAMERA_CONF_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32n6xx_hal.h"

/* Enable only IMX335 — no VD55G1 / VD66GY on this board */
#define USE_IMX335_SENSOR

#ifdef __cplusplus
}
#endif

#endif /* CMW_CAMERA_CONF_H */
