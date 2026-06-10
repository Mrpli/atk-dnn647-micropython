#define MICROPY_HW_BOARD_NAME                   "ATK-DNN647"
#define MICROPY_HW_MCU_NAME                     "STM32N647X0"

#define MICROPY_GC_STACK_ENTRY_TYPE             uint32_t
#define MICROPY_ALLOC_GC_STACK_SIZE             (128)
#define MICROPY_FATFS_EXFAT                     (1)

#define MICROPY_HW_ENABLE_INTERNAL_FLASH_STORAGE (0)
#define MICROPY_HW_HAS_SWITCH                   (1)
#define MICROPY_HW_HAS_FLASH                    (1)
#define MICROPY_HW_ENABLE_RNG                   (1)
#define MICROPY_HW_ENABLE_RTC                   (1)
#define MICROPY_HW_ENABLE_DAC                   (0)
#define MICROPY_HW_ENABLE_USB                   (1)
#define MICROPY_HW_ENABLE_SDCARD                (1)
#define MICROPY_PY_PYB_LEGACY                   (0)

#define MICROPY_BOARD_EARLY_INIT                board_early_init
#define MICROPY_BOARD_LEAVE_STANDBY             board_leave_standby()

// HSE is 48MHz, this gives a CPU frequency of 800MHz.
#define MICROPY_HW_CLK_PLLM                     (6)
#define MICROPY_HW_CLK_PLLN                     (100)
#define MICROPY_HW_CLK_PLLP1                    (1)
#define MICROPY_HW_CLK_PLLP2                    (1)
#define MICROPY_HW_CLK_PLLFRAC                  (0)

// The LSE is a 32kHz crystal.
#define MICROPY_HW_RTC_USE_LSE                  (1)
#define MICROPY_HW_RTC_USE_US                   (1)

// External SPI flash, MX25UM25645G (256Mbit = 32MB).
#define MICROPY_HW_XSPIFLASH_SIZE_BITS_LOG2     (28)

// SPI flash, block device config.
#define MICROPY_HW_BDEV_SPIFLASH                (&spi_bdev)
#define MICROPY_HW_BDEV_SPIFLASH_EXTENDED       (&spi_bdev)
#define MICROPY_HW_BDEV_SPIFLASH_CONFIG         (&spiflash_config)
#define MICROPY_HW_BDEV_SPIFLASH_OFFSET_BYTES   (4 * 1024 * 1024)
#define MICROPY_HW_BDEV_SPIFLASH_SIZE_BYTES     (4 * 1024 * 1024)

// UART buses
#define MICROPY_HW_UART1_TX                     (pyb_pin_UART1_TX)
#define MICROPY_HW_UART1_RX                     (pyb_pin_UART1_RX)
#define MICROPY_HW_UART3_TX                     (pyb_pin_UART3_TX)
#define MICROPY_HW_UART3_RX                     (pyb_pin_UART3_RX)
#define MICROPY_HW_UART7_TX                     (pyb_pin_UART7_TX)
#define MICROPY_HW_UART7_RX                     (pyb_pin_UART7_RX)
#define MICROPY_HW_UART_REPL                    (PYB_UART_1)
#define MICROPY_HW_UART_REPL_BAUD               (115200)

// I2C buses
#define MICROPY_HW_I2C2_SCL                     (pyb_pin_I2C2_SCL)
#define MICROPY_HW_I2C2_SDA                     (pyb_pin_I2C2_SDA)
#define MICROPY_HW_I2C4_SCL                     (pyb_pin_I2C4_SCL)
#define MICROPY_HW_I2C4_SDA                     (pyb_pin_I2C4_SDA)

// SPI buses
#define MICROPY_HW_SPI5_NSS                     (pyb_pin_SPI5_NSS)
#define MICROPY_HW_SPI5_SCK                     (pyb_pin_SPI5_SCK)
#define MICROPY_HW_SPI5_MISO                    (pyb_pin_SPI5_MISO)
#define MICROPY_HW_SPI5_MOSI                    (pyb_pin_SPI5_MOSI)

#define MICROPY_BANNER_MACHINE \
    MICROPY_HW_BOARD_NAME " with " MICROPY_HW_MCU_NAME "\r\n" \
    "====================================================== \r\n" \
    "    _  _____ _  __    ____ _____ __  __ _________      \r\n" \
    "   / \\|_   _| |/ /   / ___|_   _|  \\/  |___ /___ \\  \r\n" \
    "  / _ \\ | | | ' /____\\___ \\ | | | |\\/| | |_ \\ __) |\r\n" \
    " / ___ \\| | | . \\_____|__) || | | |  | |___) / __/   \r\n" \
    "/_/__ \\_\\_|_|_|\\_\\   |____/_|_|_|_| _|_|____/_____|\r\n" \
    "|  _ \\| \\ | | \\ | |      / /_ | || |___  |          \r\n" \
    "| | | |  \\| |  \\| |_____| '_ \\| || |_ / /           \r\n" \
    "| |_| | |\\  | |\\  |_____| (_) |__   _/ /             \r\n" \
    "|____/|_| \\_|_| \\_|      \\___/   |_|/_/             \r\n" \
    "====================================================== \r\n" \
    "        Author:GraysonWarner     version:v1.1          \r\n" \
    "    https://github.com/Mrpli/atk-dnn647-micropython    \r\n" \
    "====================================================== \r\n"

// LEDs: LED0=PG10, LED1=PE10 (active low).
#define MICROPY_HW_LED1                         (pyb_pin_LED0)
#define MICROPY_HW_LED2                         (pyb_pin_LED1)
#define MICROPY_HW_LED_ON(pin)                  (mp_hal_pin_low(pin))
#define MICROPY_HW_LED_OFF(pin)                 (mp_hal_pin_high(pin))

// User switch: KEY0 (PC6), active low (pressed = GND).
#define MICROPY_HW_USRSW_PIN                    (pyb_pin_KEY0)
#define MICROPY_HW_USRSW_PULL                   (GPIO_PULLUP)
#define MICROPY_HW_USRSW_EXTI_MODE              (GPIO_MODE_IT_FALLING)
#define MICROPY_HW_USRSW_PRESSED                (0)

// USB config
#define MICROPY_HW_USB_HS                       (1)
#define MICROPY_HW_USB_HS_IN_FS                 (1)
#define MICROPY_HW_USB_MAIN_DEV                 (USB_PHY_HS_ID)

// SD Card (SDMMC1)
#define MICROPY_HW_SDCARD_SDMMC                 (1)
#define MICROPY_HW_SDCARD_CK                    (pyb_pin_SDMMC1_CK)
#define MICROPY_HW_SDCARD_CMD                   (pyb_pin_SDMMC1_CMD)
#define MICROPY_HW_SDCARD_D0                    (pyb_pin_SDMMC1_D0)
#define MICROPY_HW_SDCARD_D1                    (pyb_pin_SDMMC1_D1)
#define MICROPY_HW_SDCARD_D2                    (pyb_pin_SDMMC1_D2)
#define MICROPY_HW_SDCARD_D3                    (pyb_pin_SDMMC1_D3)

#define MICROPY_HW_ENABLE_SDCARD                (1)

// Ethernet via RMII (PHY: onboard)
#define MICROPY_HW_ETH_MDC                      (pin_H5)
#define MICROPY_HW_ETH_MDIO                     (pin_F4)
#define MICROPY_HW_ETH_RMII_REF_CLK             (pin_F7)
#define MICROPY_HW_ETH_RMII_CRS_DV              (pin_F10)
#define MICROPY_HW_ETH_RMII_RXD0                (pin_F14)
#define MICROPY_HW_ETH_RMII_RXD1                (pin_F15)
#define MICROPY_HW_ETH_RMII_TX_EN               (pin_F11)
#define MICROPY_HW_ETH_RMII_TXD0                (pin_F12)
#define MICROPY_HW_ETH_RMII_TXD1                (pin_F13)

/******************************************************************************/
// Bootloader configuration

#define MBOOT_BOARD_EARLY_INIT(initial_r0)      mboot_board_early_init()

#define MBOOT_SPIFLASH_CS                       (pyb_pin_XSPIM_P2_CS)
#define MBOOT_SPIFLASH_SCK                      (pyb_pin_XSPIM_P2_SCK)
#define MBOOT_SPIFLASH_MOSI                     (pyb_pin_XSPIM_P2_IO0)
#define MBOOT_SPIFLASH_MISO                     (pyb_pin_XSPIM_P2_IO1)
#define MBOOT_SPIFLASH_ADDR                     (0x70000000)
#define MBOOT_SPIFLASH_BYTE_SIZE                (32 * 1024 * 1024)
#define MBOOT_SPIFLASH_LAYOUT                   "/0x70000000/8192*4Kg"
#define MBOOT_SPIFLASH_ERASE_BLOCKS_PER_PAGE    (1)
#define MBOOT_SPIFLASH_SPIFLASH                 (&spi_bdev.spiflash)
#define MBOOT_SPIFLASH_CONFIG                   (&spiflash_config)

/******************************************************************************/
// Function and variable declarations

extern const struct _mp_spiflash_config_t spiflash_config;
extern struct _spi_bdev_t spi_bdev;

void mboot_board_early_init(void);
void mboot_board_entry_init(void);

void board_early_init(void);
void board_leave_standby(void);
