/*
 * ISP middleware configuration for MicroPython / NUCLEO-N657X0-Q.
 * Enables the software AEC and AWB algorithms (require linking
 * libn6-evision-st-ae_gcc.a and libn6-evision-awb_gcc.a).
 */

#ifndef __ISP_CONF_H
#define __ISP_CONF_H

#define ISP_MW_SW_AEC_ALGO_SUPPORT
#define ISP_MW_SW_AWB_ALGO_SUPPORT

#endif /* __ISP_CONF_H */
