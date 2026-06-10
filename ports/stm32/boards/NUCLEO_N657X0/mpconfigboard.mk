# Without mboot, the main firmware must fit in 512k flash, will be copied to SRAM by
# the hardware bootloader, and will run from SRAM.  With mboot, the main firmware can
# be much larger and will run from flash via XSPI in memory-mapped mode.
USE_MBOOT ?= 1

MCU_SERIES = n6
CMSIS_MCU = STM32N657xx
AF_FILE = boards/stm32n657_af.csv
ifeq ($(BUILDING_MBOOT),1)
SYSTEM_FILE = $(STM32LIB_CMSIS_BASE)/Source/Templates/system_stm32$(MCU_SERIES)xx_fsbl.o
else
SYSTEM_FILE = $(STM32LIB_CMSIS_BASE)/Source/Templates/system_stm32$(MCU_SERIES)xx_s.o
endif
STM32_N6_HEADER_VERSION = 2.3
DKEL = $(STM32_CUBE_PROGRAMMER)/bin/ExternalLoader/MX25UM51245G_STM32N6570-NUCLEO.stldr

ifeq ($(USE_MBOOT),1)
LD_FILES = boards/stm32n657x0.ld boards/common_n6_flash.ld
TEXT0_ADDR = 0x70080000
else
LD_FILES = boards/stm32n657x0.ld boards/common_basic.ld
TEXT0_ADDR = 0x34180400
endif

# MicroPython settings
MICROPY_FLOAT_IMPL = double
MICROPY_PY_LWIP = 1
MICROPY_PY_SSL = 1
MICROPY_SSL_MBEDTLS = 1

# ---- IMX335 camera driver (main firmware only, not mboot) ------------------
# CAMERA_DIR is relative to ports/stm32/ (same convention as BOARD_DIR)
ifneq ($(BUILDING_MBOOT),1)
CAMERA_DIR = $(BOARD_DIR)/camera

SRC_C += \
    $(CAMERA_DIR)/CMW/cmw_camera.c \
    $(CAMERA_DIR)/CMW/cmw_utils.c \
    $(CAMERA_DIR)/CMW/sensors/cmw_imx335.c \
    $(CAMERA_DIR)/CMW/sensors/imx335/imx335.c \
    $(CAMERA_DIR)/CMW/sensors/imx335/imx335_reg.c \
    $(CAMERA_DIR)/ISP/Src/isp_algo.c \
    $(CAMERA_DIR)/ISP/Src/isp_cmd_parser.c \
    $(CAMERA_DIR)/ISP/Src/isp_core.c \
    $(CAMERA_DIR)/ISP/Src/isp_services.c \
    $(CAMERA_DIR)/modcamera.c \
    $(CAMERA_DIR)/stubs.c

# Include paths — relative to ports/stm32/, same convention as -I$(BOARD_DIR)
CFLAGS += \
    -I$(CAMERA_DIR)/CMW \
    -I$(CAMERA_DIR)/CMW/sensors \
    -I$(CAMERA_DIR)/CMW/sensors/imx335 \
    -I$(CAMERA_DIR)/ISP/Inc

# Precompiled ST ISP algorithm libraries (AEC + AWB)
# Absolute path via $(TOP) so the linker finds them regardless of build CWD
LIBS += \
    $(TOP)/ports/stm32/$(CAMERA_DIR)/ISP/Lib/libn6-evision-st-ae_gcc.a \
    $(TOP)/ports/stm32/$(CAMERA_DIR)/ISP/Lib/libn6-evision-awb_gcc.a

# math library needed by the AWB ISP library (powf)
# Use absolute path from multilib to avoid architecture mismatch with -nostdlib
LIBS += $(shell $(CC) $(CFLAGS) -print-file-name=libm.a)
endif
