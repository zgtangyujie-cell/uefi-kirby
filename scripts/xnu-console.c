/* Draw the kernel's printf() output on the frame buffer.
 *
 * Built freestanding by patch-xnu-console.py and placed in padding of a COPY of
 * the kernel; printf() is redirected here. The kernel's own video console never
 * starts on this board, so without this every kernel message goes nowhere.
 *
 * State: this code lives in the kernel's read-only text, so a writable global
 * would fault on its first store. The cursor therefore lives in the last row of
 * the frame buffer, two pixels that normal output never reaches.
 */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned char u8;

struct vc_info {
  u32 v_height, v_width, v_depth, v_rowbytes;
  u64 v_baseaddr;
};

/*
 * _vinfo lives in BSS and is only filled by initialize_screen, which does not
 * produce a usable console on this board (that is why the vc_info guard in
 * console_printf_main rejects every message and the panel stays blank).  But
 * PE_state.video is filled unconditionally by PE_init_platform, straight from
 * boot_args->Video, and DarwinBoot has already put the real numbers there
 * (measured: base 0xD5100000, 1600x2560, rowBytes 6400, depth 32).
 *
 * PE_Video field offsets verified in _initialize_screen's own loads:
 *   +0x00 base (ldr x), +0x08 rowBytes (ldr w), +0x10 width, +0x18 height,
 *   +0x20 depth.  Every slot is 8 bytes wide with only the low half read.
 *
 * So when PE_VIDEO_ADDR is supplied, read the geometry from there instead of
 * from _vinfo.  Same four sanity checks, so a bad pointer still draws nothing.
 */
#ifdef PE_VIDEO_ADDR
struct pe_video {
  u64 base, rowbytes, width, height, depth;
};
#endif

static int console_geometry (u8 **base, u32 *rb, u32 *w, u32 *h)
{
#ifdef PE_VIDEO_ADDR
  volatile struct pe_video *pv = (volatile struct pe_video *)PE_VIDEO_ADDR;

  if (pv->base == 0 || pv->depth != 32 || pv->rowbytes == 0 || pv->width < 8) {
    return 0;
  }
  *base = (u8 *)pv->base;
  *rb   = (u32)pv->rowbytes;
  *w    = (u32)pv->width;
  *h    = (u32)pv->height;
  return 1;
#else
  volatile struct vc_info *v = (volatile struct vc_info *)VINFO;

  if (v->v_baseaddr == 0 || v->v_depth != 32 || v->v_rowbytes == 0 || v->v_width < 8) {
    return 0;
  }
  *base = (u8 *)v->v_baseaddr;
  *rb   = v->v_rowbytes;
  *w    = v->v_width;
  *h    = v->v_height;
  return 1;
#endif
}

#define SCALE 2

extern const u64 gFont[];

struct ctx {
  u8  *base;
  u32 rb, w, h, x, y;
};

static void scroll (struct ctx *g)
{
  const u32 line = 14 * SCALE;
  u32 row, col;

  for (row = 0; row + line < g->h; row++) {
    for (col = 0; col < g->w; col++) {
      u32 from = *(volatile u32 *)(g->base + (u64)(row + line) * g->rb + (u64)col * 4);
      *(volatile u32 *)(g->base + (u64)row * g->rb + (u64)col * 4) = from;
    }
  }
  for (; row < g->h; row++) {
    for (col = 0; col < g->w; col++) {
      *(volatile u32 *)(g->base + (u64)row * g->rb + (u64)col * 4) = 0;
    }
  }
  g->y = g->h - line;
}

static void put (struct ctx *g, u8 c)
{
  const u32 cell = 6 * SCALE, line = 14 * SCALE;
  u32 row, col, dy, dx;

  if (c == '\n') {
    g->x = 0;
    g->y += line;
    if (g->y + line > g->h) {
      scroll (g);
    }
    return;
  }
  if (c == '\t') {
    g->x += 4 * cell;
    return;
  }
  if (c < 32 || c > 126) {
    return;
  }
  if (g->x + cell > g->w) {
    g->x = 0;
    g->y += line;
  }
  if (g->y + line > g->h) {
    scroll (g);
  }
  u64 glyph = gFont[c - 32];
  u32 top = (u32)(glyph >> 32), bottom = (u32)glyph;
  for (row = 0; row < 12; row++) {
    u32 data = (row < 6) ? (top >> (row * 5)) : (bottom >> ((row - 6) * 5));
    for (col = 0; col < 5; col++) {
      if ((data >> col) & 1) {
        for (dy = 0; dy < SCALE; dy++) {
          for (dx = 0; dx < SCALE; dx++) {
            *(volatile u32 *)(g->base + (u64)(g->y + row * SCALE + dy) * g->rb +
                              (u64)(g->x + col * SCALE + dx) * 4) = 0xFFFFFFFFu;
          }
        }
      }
    }
  }
  g->x += cell;
}

static void number (struct ctx *g, u64 value, u32 base, u32 width, int zero)
{
  u8  digits[24];
  u32 n = 0, i;

  do {
    u32 d = (u32)(value % base);
    digits[n++] = (u8)(d < 10 ? '0' + d : 'a' + d - 10);
    value /= base;
  } while (value && n < 24);
  for (i = n; i < width; i++) {
    put (g, zero ? '0' : ' ');
  }
  while (n) {
    put (g, digits[--n]);
  }
}

/* Only touch strings that the active translation actually maps. */
static int readable (const char *s)
{
  u64 a = (u64)s, par;
  if (a < 0xffff000000000000UL) return 0;
  __asm__ volatile ("at s1e1r, %1; isb; mrs %0, par_el1" : "=r" (par) : "r" (a) : "memory");
  return !(par & 1) && ((par >> 60) != 0);
}

static u32 format (struct ctx *g, const char *fmt, const u64 *args)
{
  u32 i, used = 0, emitted = 0;

  for (i = 0; i < 2000 && fmt[i]; i++) {
    u8 c = (u8)fmt[i];
    if (c != '%') {
      put (g, c);
      emitted++;
      continue;
    }
    u32 width = 0;
    int zero = 0;
    c = (u8)fmt[++i];
    if (c == '0') {
      zero = 1;
      c = (u8)fmt[++i];
    }
    while (c >= '0' && c <= '9') {
      width = width * 10 + (c - '0');
      c = (u8)fmt[++i];
    }
    u32 precision = 4000;
    if (c == '.') {
      precision = 0;
      c = (u8)fmt[++i];
      while (c >= '0' && c <= '9') {
        if (precision < 4000) precision = precision * 10 + (c - '0');
        c = (u8)fmt[++i];
      }
      if (precision > 4000) precision = 4000;
    }
    if (width > 256) width = 256;
    while (c == 'l' || c == 'z' || c == 'h') {
      c = (u8)fmt[++i];
    }
    if (c == '%') {
      put (g, '%');
      emitted++;
      continue;
    }
    if (c == 0) {
      break;
    }
    u64 v = args[used++];
    if (c == 's') {
      const char *s = (const char *)v;
      u32 k;
      for (k = 0; k < precision; k++) {
        if (!readable (s + k) || s[k] == 0) {
          break;
        }
        put (g, (u8)s[k]);
        emitted++;
      }
    } else if (c == 'c') {
      put (g, (u8)v);
      emitted++;
    } else if (c == 'p') {
      put (g, '0');
      put (g, 'x');
      number (g, v, 16, 16, 1);
      emitted += 18;
    } else if (c == 'd' || c == 'i') {
      if ((long)v < 0) {
        put (g, '-');
        v = (u64)(-(long)v);
        emitted++;
      }
      number (g, v, 10, width, zero);
      emitted += width;
    } else if (c == 'u') {
      number (g, v, 10, width, zero);
      emitted += width;
    } else if (c == 'x' || c == 'X') {
      number (g, v, 16, width, zero);
      emitted += width;
    } else if (c == 'o') {
      number (g, v, 8, width, zero);
      emitted += width;
    } else {
      put (g, '%');
      put (g, c);
      emitted += 2;
    }
  }
  return emitted;
}

__attribute__((used, section(".text.b_main"))) u64 console_printf_main (const char *fmt, const u64 *args)
{
  struct ctx g;
  volatile u32 *cursor;
  u32 saved;

  if (fmt == 0) {
    return 0;
  }
  if (!console_geometry (&g.base, &g.rb, &g.w, &g.h)) {
    return 0;
  }

  /* Cursor lives in the last row: x in the second to last pixel, y in the last. */
  cursor = (volatile u32 *)(g.base + (u64)(g.h - 1) * g.rb + (u64)(g.w - 2) * 4);
  saved = cursor[0] ^ 0x434F4E53u;
  g.x = saved & 0xFFFFu;
  g.y = (saved >> 16) & 0xFFFFu;
  if (g.x >= g.w || g.y + 14 * SCALE > g.h || (saved == 0 && cursor[1] != 0x4C4F4731u)) {
    g.x = 0;
    g.y = 0;
    cursor[1] = 0x4C4F4731u;
  }

  u32 written = format (&g, fmt, args);
  cursor[0] = (((g.y & 0xFFFFu) << 16) | (g.x & 0xFFFFu)) ^ 0x434F4E53u;
  __asm__ volatile ("dsb sy");
  return written;
}

/* printf() keeps the stack pointer, which addresses the variadic arguments. */
__attribute__((naked, used, section(".text.a_entry"))) void console_printf (const char *fmt)
{
  __asm__ volatile ("mov x1, sp\n\tb console_printf_main");
}


/* --- heartbeat -------------------------------------------------------------
 *
 * idle_thread() calls machine_idle() in a loop; the patcher points that call
 * here, so the screen keeps moving once the log goes quiet. Time comes from the
 * ARM generic counter: the cadence does not depend on how often the CPU idles.
 */
#define TIMEBASE 19200000UL
#define HEARTBEAT_SECONDS 5

static u64 counter (void)
{
  u64 v;
  __asm__ volatile ("isb; mrs %0, cntpct_el0" : "=r" (v) : : "memory");
  return v;
}

static void load_cursor (struct ctx *g)
{
  volatile u32 *cursor = (volatile u32 *)(g->base + (u64)(g->h - 1) * g->rb + (u64)(g->w - 2) * 4);
  u32 saved = cursor[0] ^ 0x434F4E53u;
  g->x = saved & 0xFFFFu;
  g->y = (saved >> 16) & 0xFFFFu;
  if (g->x >= g->w || g->y + 14 * SCALE > g->h) {
    g->x = 0;
    g->y = 0;
  }
}

static void store_cursor (struct ctx *g)
{
  volatile u32 *cursor = (volatile u32 *)(g->base + (u64)(g->h - 1) * g->rb + (u64)(g->w - 2) * 4);
  cursor[0] = (((g->y & 0xFFFFu) << 16) | (g->x & 0xFFFFu)) ^ 0x434F4E53u;
}

__attribute__((used, section(".text.c_beat"))) void heartbeat_wrapper (void)
{
  void (*idle) (void) = (void (*) (void)) MACHINE_IDLE;
  struct ctx g;
  volatile u32 *slot;
  u32 now, last;

  idle ();

  if (!console_geometry (&g.base, &g.rb, &g.w, &g.h)) {
    return;
  }
  now = (u32)(counter () / TIMEBASE);

  slot = (volatile u32 *)(g.base + (u64)(g.h - 1) * g.rb + (u64)(g.w - 3) * 4);
  last = *slot ^ 0x42454154u;
  if (last == 0 || last > now || now - last < HEARTBEAT_SECONDS) {
    *slot = now ^ 0x42454154u;
    return;
  }
  *slot = now ^ 0x42454154u;

  load_cursor (&g);
  put (&g, '\n');
  const char *label = "[XNU] alive ";
  while (*label) {
    put (&g, (u8)*label++);
  }
  number (&g, now, 10, 1, 0);
  put (&g, 's');
  put (&g, ' ');
  put (&g, 'p');
  put (&g, 'g');
  number (&g, *(volatile const u32 *)PAGE_TOTAL, 10, 1, 0);
  put (&g, '/');
  number (&g, *(volatile const u32 *)PAGE_FREE, 10, 1, 0);
  store_cursor (&g);
}

#include "Font.h"
__attribute__((section(".text.z_font"))) const u64 gFont[] = GLYPH_FONT;
