/*
 * Minimal stubs for newlib math functions needed by the precompiled
 * ISP AWB library (libn6-evision-awb_gcc.a).
 *
 * Provides __errno (referenced by libm.a's powf error path) so that
 * the linker does not pull in the full libc just for this symbol.
 */

int __errno_val;

int *__errno(void) {
    return &__errno_val;
}
