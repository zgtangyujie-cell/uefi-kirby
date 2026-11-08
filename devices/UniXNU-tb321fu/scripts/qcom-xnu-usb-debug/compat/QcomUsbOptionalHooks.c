/* SPDX-License-Identifier: MIT
 *
 * Weak definitions for the two board-optional hooks QcomXnuUsbDebug.c calls.
 *
 * That file declares both as `__attribute__((weak_import))`, which is a dyld
 * concept: a statically linked kernel has no dyld, so ld64 still reports them
 * as undefined and the final link fails with
 *
 *     Undefined symbols for architecture arm64:
 *       "_boot_progress_persist", referenced from _qcom_usb_debug_init
 *       "_boot_reset_bootloader",  referenced from _qcom_usb_debug_control_reset_now
 *
 * measured on run 42472297280.  Weak definitions make the archive
 * self-sufficient: Mach-O gives a strong definition precedence, so a kernel
 * that really provides either hook still wins, and a kernel that does not gets
 * exactly the behaviour the weak_import path intends —
 *   - the persistent diagnostic row is simply not drawn (boot_progress_persist),
 *   - the reboot reports `QCOM USB REBOOT refused: rc=-01` and then falls back
 *     to platform_smc_reset(), which is the measured PSCI path (see Sm8650.h).
 */
#include <stdint.h>

__attribute__((weak)) void
boot_progress_persist(const char *text, uint32_t colour)
{
	(void)text;
	(void)colour;
}

__attribute__((weak)) int
boot_reset_bootloader(char *text, unsigned size)
{
	if (text != (char *)0 && size > 0) {
		text[0] = '\0';
	}
	return -1;
}
