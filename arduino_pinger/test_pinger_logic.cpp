// Host checks for frequency rounding, serial numbers, limits, and start/stop.
// This does not program a board and is not a hardware test.

#if defined(_MSC_VER)
#define _CRT_SECURE_NO_WARNINGS
#endif

#include <stdio.h>
#include <stddef.h>
#include <stdint.h>

#include "robosub_pinger/pinger_logic.h"

static int g_failures = 0;

static const int kFailCap = 48;
static char g_fail_names[48][80];

static void note_failure(const char *name) {
  printf("FAIL %s\n", name);
  if (g_failures < kFailCap) {
    size_t i = 0;
    while (name[i] != '\0' && i + 1 < sizeof(g_fail_names[0])) {
      g_fail_names[g_failures][i] = name[i];
      i++;
    }
    g_fail_names[g_failures][i] = '\0';
  }
  g_failures++;
}

static void expect_true(bool cond, const char *name) {
  if (!cond) {
    note_failure(name);
  }
}

static void expect_eq_u32(uint32_t got, uint32_t want, const char *name) {
  if (got != want) {
    printf(" got %lu want %lu\n", (unsigned long)got, (unsigned long)want);
    note_failure(name);
  }
}

static uint32_t abs_diff_u32(uint32_t left, uint32_t right) {
  return left > right ? left - right : right - left;
}

static void test_anchor_frequencies() {
  struct {
    uint16_t requested;
    uint16_t ocr;
    uint32_t hz;
    uint8_t hundredths;
  } anchors[] = {
      {25000, 319, 25000, 0},
      {30000, 266, 29962, 54},
      {35000, 228, 34934, 49},
      {40000, 199, 40000, 0},
  };
  for (unsigned i = 0; i < sizeof(anchors) / sizeof(anchors[0]); i++) {
    uint16_t ocr = pingerOcrForFrequency(PINGER_F_CPU_HZ, anchors[i].requested);
    uint32_t hz = 0;
    uint8_t frac = 0;
    pingerActualFrequency(PINGER_F_CPU_HZ, ocr, &hz, &frac);
    expect_eq_u32(ocr, anchors[i].ocr, "ocr");
    expect_eq_u32(hz, anchors[i].hz, "hz");
    expect_eq_u32(frac, anchors[i].hundredths, "hundredths");
    expect_eq_u32(hz, PINGER_F_CPU_HZ / (2UL * ((uint32_t)ocr + 1UL)), "formula");
  }
}

static void test_rounding_is_nearest() {
  for (uint16_t freq = PINGER_FREQ_MIN_HZ; freq <= PINGER_FREQ_MAX_HZ; freq = (uint16_t)(freq + PINGER_FREQ_STEP_HZ)) {
    uint16_t ocr = pingerOcrForFrequency(PINGER_F_CPU_HZ, freq);
    uint32_t den = 2UL * (uint32_t)freq;
    uint32_t ticks = (uint32_t)ocr + 1UL;
    uint32_t err = abs_diff_u32(ticks * den, PINGER_F_CPU_HZ);
    uint32_t err_lo = abs_diff_u32((ticks - 1UL) * den, PINGER_F_CPU_HZ);
    uint32_t err_hi = abs_diff_u32((ticks + 1UL) * den, PINGER_F_CPU_HZ);
    expect_true(err <= err_lo && err <= err_hi, "nearest divider");
    expect_true((freq % PINGER_FREQ_STEP_HZ) == 0, "step grid");
  }
}

static void test_numbers() {
  uint16_t value = 99;
  expect_true(pingerParseU16("30000", &value) == PINGER_NUM_OK && value == 30000, "plain");
  expect_true(pingerParseU16("0", &value) == PINGER_NUM_OK && value == 0, "zero");
  expect_true(pingerParseU16("65535", &value) == PINGER_NUM_OK && value == 65535, "max u16");
  expect_true(pingerParseU16("10  ", &value) == PINGER_NUM_OK && value == 10, "trailing space");
  expect_true(pingerParseU16("", &value) == PINGER_NUM_EMPTY, "empty");
  expect_true(pingerParseU16("+30000", &value) == PINGER_NUM_SIGN, "plus");
  expect_true(pingerParseU16("-1", &value) == PINGER_NUM_SIGN, "minus");
  expect_true(pingerParseU16("-0", &value) == PINGER_NUM_SIGN, "minus zero");
  expect_true(pingerParseU16("30000x", &value) == PINGER_NUM_MALFORMED, "trailing char");
  expect_true(pingerParseU16("30000 extra", &value) == PINGER_NUM_MALFORMED, "trailing word");
  expect_true(pingerParseU16("12.5", &value) == PINGER_NUM_MALFORMED, "decimal");
  expect_true(pingerParseU16("0x10", &value) == PINGER_NUM_MALFORMED, "hex");
  expect_true(pingerParseU16("65536", &value) == PINGER_NUM_OVERFLOW, "65536");
  expect_true(pingerParseU16("999999999999", &value) == PINGER_NUM_OVERFLOW, "huge");
}

static PingerLine parse_copy(const char *text) {
  char buf[64];
  size_t n = 0;
  while (n + 1 < sizeof(buf) && text[n] != '\0') {
    buf[n] = text[n];
    n++;
  }
  buf[n] = '\0';
  return pingerParseLine(buf);
}

static void test_lines() {
  PingerLine line = parse_copy("stop");
  expect_true(line.command == PINGER_CMD_STOP && !line.extra, "stop case");
  line = parse_copy("STOP now");
  expect_true(line.command == PINGER_CMD_STOP && line.extra, "stop extra");
  line = parse_copy("FREQ 30000");
  expect_true(line.command == PINGER_CMD_FREQ && line.number == PINGER_NUM_OK && line.value == 30000, "freq ok");
  line = parse_copy("FREQ -30000");
  expect_true(line.command == PINGER_CMD_FREQ && line.number == PINGER_NUM_SIGN, "freq sign");
  line = parse_copy("FREQ");
  expect_true(line.command == PINGER_CMD_FREQ && line.number == PINGER_NUM_EMPTY, "freq missing");
  line = parse_copy("nope");
  expect_true(line.command == PINGER_CMD_UNKNOWN, "unknown");
  line = parse_copy("   ");
  expect_true(line.command == PINGER_CMD_EMPTY, "blank");
}

static void test_limits_and_state() {
  PingerSettings settings;
  pingerSettingsDefault(&settings);
  expect_eq_u32(settings.freq_hz, 30000, "default freq");
  expect_eq_u32(settings.period_ms, 1000, "default period");
  expect_eq_u32(settings.pulse_ms, 10, "default pulse");
  expect_true(!settings.running, "default stopped");

  expect_true(pingerSetFreq(&settings, 24500) == PINGER_APPLY_FREQ && settings.freq_hz == 30000, "freq low");
  expect_true(pingerSetFreq(&settings, 40500) == PINGER_APPLY_FREQ, "freq high");
  expect_true(pingerSetFreq(&settings, 30250) == PINGER_APPLY_FREQ && settings.freq_hz == 30000, "freq step");
  expect_true(pingerSetFreq(&settings, 25000) == PINGER_APPLY_OK && settings.freq_hz == 25000, "freq min");
  expect_true(pingerSetFreq(&settings, 40000) == PINGER_APPLY_OK && settings.freq_hz == 40000, "freq max");

  expect_true(pingerSetPeriod(&settings, 499) == PINGER_APPLY_PERIOD && settings.period_ms == 1000, "period low");
  expect_true(pingerSetPeriod(&settings, 2001) == PINGER_APPLY_PERIOD, "period high");
  expect_true(pingerSetPeriod(&settings, 500) == PINGER_APPLY_OK, "period min");
  expect_true(pingerSetPeriod(&settings, 2000) == PINGER_APPLY_OK, "period max");

  expect_true(pingerSetPulse(&settings, 0) == PINGER_APPLY_PULSE, "pulse zero");
  expect_true(pingerSetPulse(&settings, 101) == PINGER_APPLY_PULSE, "pulse high");
  expect_true(pingerSetPulse(&settings, 1) == PINGER_APPLY_OK && settings.pulse_ms == 1, "pulse min");
  expect_true(pingerSetPulse(&settings, 100) == PINGER_APPLY_OK, "pulse max");
  // Public ranges cannot make pulse >= period (100 ms vs 500 ms). Force the
  // guard anyway so a future limit change cannot drop it silently.
  settings.pulse_ms = 80;
  expect_true(pingerSetPeriod(&settings, 80) == PINGER_APPLY_PERIOD, "period still below minimum");
  settings.period_ms = 80;
  expect_true(pingerSetPulse(&settings, 80) == PINGER_APPLY_NOT_SHORTER && settings.pulse_ms == 80, "pulse not shorter");
  expect_true(pingerSetPeriod(&settings, 500) == PINGER_APPLY_OK && settings.period_ms == 500, "period restored");
  settings.pulse_ms = 600;
  expect_true(pingerSetPeriod(&settings, 500) == PINGER_APPLY_NOT_SHORTER && settings.period_ms == 500, "period not shorter than pulse");
  settings.pulse_ms = 10;

  expect_true(pingerStart(&settings) == PINGER_APPLY_OK && settings.running, "start");
  expect_true(pingerStart(&settings) == PINGER_APPLY_ALREADY_RUNNING, "start twice");
  expect_true(pingerSetFreq(&settings, 35000) == PINGER_APPLY_OK && settings.running, "freq while running");
  pingerStop(&settings);
  expect_true(!settings.running, "stop");
  pingerStop(&settings);
  expect_true(!settings.running, "stop twice");
  expect_true(pingerStart(&settings) == PINGER_APPLY_OK, "start after stop");
}

static int32_t percent_e4(uint16_t requested, uint16_t ocr) {
  int64_t den = 2LL * ((int64_t)ocr + 1LL);
  int64_t delta = (int64_t)PINGER_F_CPU_HZ - (int64_t)requested * den;
  int64_t numer = 1000000LL * delta;
  int64_t denom = den * (int64_t)requested;
  int64_t q = numer / denom;
  int64_t r = numer % denom;
  int64_t ar = r < 0 ? -r : r;
  int64_t ad = denom < 0 ? -denom : denom;
  if (ar * 2 >= ad) {
    q += numer < 0 ? -1 : 1;
  }
  return (int32_t)q;
}

static void format_percent(char *dst, size_t n, int32_t e4) {
  int32_t abs_e4 = e4 < 0 ? -e4 : e4;
  snprintf(dst, n, "%s%ld.%04ld%%", e4 < 0 ? "-" : "", (long)(abs_e4 / 10000), (long)(abs_e4 % 10000));
}

struct FreqRow {
  uint16_t requested;
  uint16_t ocr;
  uint32_t hz;
  uint32_t frac4;
  uint8_t hundredths;
  int32_t error_e4;
  bool pass;
};

static FreqRow g_freq_rows[40];
static int g_freq_count = 0;
static int g_freq_worst_index = 0;

static void test_frequency_grid() {
  g_freq_count = 0;
  int32_t worst = -1;
  for (uint16_t freq = PINGER_FREQ_MIN_HZ; freq <= PINGER_FREQ_MAX_HZ; freq = (uint16_t)(freq + PINGER_FREQ_STEP_HZ)) {
    FreqRow *row = &g_freq_rows[g_freq_count];
    row->requested = freq;
    row->pass = true;
    PingerSettings settings;
    pingerSettingsDefault(&settings);
    if (pingerSetFreq(&settings, freq) != PINGER_APPLY_OK || settings.freq_hz != freq) {
      expect_true(false, "grid setFreq");
      row->pass = false;
    }
    char line_text[24];
    snprintf(line_text, sizeof(line_text), "FREQ %u", (unsigned)freq);
    PingerLine parsed = parse_copy(line_text);
    if (parsed.command != PINGER_CMD_FREQ || parsed.number != PINGER_NUM_OK || parsed.value != freq) {
      expect_true(false, "grid parse");
      row->pass = false;
    }
    row->ocr = pingerOcrForFrequency(PINGER_F_CPU_HZ, freq);
    uint32_t den = 2UL * ((uint32_t)row->ocr + 1UL);
    uint32_t hz = PINGER_F_CPU_HZ / den;
    uint32_t rem = PINGER_F_CPU_HZ % den;
    uint32_t printed_hz = 0;
    uint8_t printed_frac = 0;
    pingerActualFrequency(PINGER_F_CPU_HZ, row->ocr, &printed_hz, &printed_frac);
    row->hz = hz;
    row->frac4 = (rem * 10000UL) / den;
    row->hundredths = (uint8_t)((rem * 100UL) / den);
    if (printed_hz != hz || printed_frac != row->hundredths) {
      expect_true(false, "grid printed hz");
      row->pass = false;
    }
    row->error_e4 = percent_e4(freq, row->ocr);
    int32_t abs_error = row->error_e4 < 0 ? -row->error_e4 : row->error_e4;
    if (g_freq_count == 0 || abs_error > worst) {
      worst = abs_error;
      g_freq_worst_index = g_freq_count;
    }
    g_freq_count++;
  }
  expect_eq_u32((uint32_t)g_freq_count, 31, "grid count");
  expect_eq_u32((uint32_t)g_freq_rows[0].ocr, 319, "grid 25k ocr");
  expect_eq_u32(g_freq_rows[0].error_e4 < 0 ? (uint32_t)(-g_freq_rows[0].error_e4) : (uint32_t)g_freq_rows[0].error_e4, 0, "grid 25k error");
  expect_eq_u32((uint32_t)(g_freq_rows[10].requested), 30000, "grid 30k index");
  expect_true(g_freq_rows[10].error_e4 == -1248, "grid 30k error");
  expect_true(g_freq_rows[20].requested == 35000 && g_freq_rows[20].error_e4 == -1871, "grid 35k error");
  expect_true(g_freq_rows[29].requested == 39500 && g_freq_rows[29].error_e4 == -2307, "grid 39.5k error");
  expect_true(g_freq_rows[4].requested == 27000 && g_freq_rows[4].error_e4 == 1001, "grid 27k error");
  expect_true(g_freq_rows[30].requested == 40000 && g_freq_rows[30].error_e4 == 0, "grid 40k error");
}

static bool same_settings(const PingerSettings *left, const PingerSettings *right) {
  return left->freq_hz == right->freq_hz && left->period_ms == right->period_ms && left->pulse_ms == right->pulse_ms &&
         left->running == right->running;
}

// Mirrors handleLine's effect on PingerSettings. Pin and serial actions stay in the sketch.
static bool apply_line(PingerSettings *settings, const char *text) {
  PingerLine line = parse_copy(text);
  if (line.command == PINGER_CMD_EMPTY) {
    return true;
  }
  if (line.command == PINGER_CMD_UNKNOWN || line.extra) {
    return false;
  }
  if (line.command == PINGER_CMD_HELP || line.command == PINGER_CMD_STATUS || line.command == PINGER_CMD_TEST) {
    return true;
  }
  if (line.command == PINGER_CMD_START) {
    return pingerStart(settings) == PINGER_APPLY_OK;
  }
  if (line.command == PINGER_CMD_STOP) {
    pingerStop(settings);
    return true;
  }
  if (line.number != PINGER_NUM_OK) {
    return false;
  }
  if (line.command == PINGER_CMD_FREQ) {
    return pingerSetFreq(settings, line.value) == PINGER_APPLY_OK;
  }
  if (line.command == PINGER_CMD_PERIOD) {
    return pingerSetPeriod(settings, line.value) == PINGER_APPLY_OK;
  }
  return pingerSetPulse(settings, line.value) == PINGER_APPLY_OK;
}

static void expect_reject(const char *text, const char *name) {
  PingerSettings settings;
  pingerSettingsDefault(&settings);
  PingerSettings before = settings;
  expect_true(!apply_line(&settings, text) && same_settings(&settings, &before), name);
}

static void test_more_commands() {
  PingerSettings settings;
  pingerSettingsDefault(&settings);
  expect_true(apply_line(&settings, "help") && !settings.running && settings.freq_hz == 30000, "help no change");
  expect_true(apply_line(&settings, "\tSTATUS") && settings.period_ms == 1000, "status no change");
  expect_true(apply_line(&settings, "TeSt") && settings.pulse_ms == 10, "test no change");
  expect_true(apply_line(&settings, "START") && settings.running, "start command");
  expect_true(!apply_line(&settings, "START") && settings.running, "second start");
  expect_true(apply_line(&settings, "StOp") && !settings.running, "mixed stop");
  expect_true(apply_line(&settings, "STOP") && !settings.running, "stop while stopped");
  expect_true(apply_line(&settings, "freq 25000") && settings.freq_hz == 25000, "freq lower");
  expect_true(apply_line(&settings, "FREQ\t40000") && settings.freq_hz == 40000, "freq tab");
  expect_true(apply_line(&settings, "FREQ 040000") && settings.freq_hz == 40000, "freq leading zeros");
  expect_true(apply_line(&settings, "period 500") && settings.period_ms == 500, "period lower");
  expect_true(apply_line(&settings, "PERIOD 2000") && settings.period_ms == 2000, "period upper");
  expect_true(apply_line(&settings, "PULSE 1") && settings.pulse_ms == 1, "pulse lower");
  expect_true(apply_line(&settings, "pulse 100") && settings.pulse_ms == 100, "pulse upper");
  expect_true(apply_line(&settings, "  PERIOD   1000") && settings.period_ms == 1000, "period spaces");

  expect_reject("HELP extra", "help extra");
  expect_reject("STATUS\tnow", "status extra");
  expect_reject("TEST 1", "test extra");
  expect_reject("START please", "start extra");
  expect_reject("STOP!", "stop bang");
  expect_reject("RUN", "run");
  expect_reject("FREQ", "freq missing command");
  expect_reject("FREQ +25000", "freq plus");
  expect_reject("FREQ -25000", "freq minus");
  expect_reject("FREQ 24999", "freq below");
  expect_reject("FREQ 40001", "freq above");
  expect_reject("FREQ 50000", "freq 50000");
  expect_reject("FREQ 65535", "freq 65535");
  expect_reject("FREQ 65536", "freq overflow");
  expect_reject("FREQ 30000 extra", "freq trailing");
  expect_reject("FREQ 30000.0", "freq decimal");
  expect_reject("PERIOD", "period missing");
  expect_reject("PERIOD +1000", "period plus");
  expect_reject("PERIOD -1", "period minus");
  expect_reject("PERIOD 499", "period below");
  expect_reject("PERIOD 2001", "period above");
  expect_reject("PERIOD 65535", "period 65535");
  expect_reject("PERIOD 65536", "period overflow");
  expect_reject("PERIOD 1000x", "period junk");
  expect_reject("PULSE", "pulse missing");
  expect_reject("PULSE +10", "pulse plus");
  expect_reject("PULSE -5", "pulse minus");
  expect_reject("PULSE 0", "pulse zero command");
  expect_reject("PULSE 101", "pulse above");
  expect_reject("PULSE 1.5", "pulse decimal");
  expect_reject("PULSE 000", "pulse zeros");
  expect_reject("PULSE 999999", "pulse huge");
}

static void test_schedule_and_rollover() {
  expect_eq_u32(pingerElapsedUs(0, 0), 0, "elapsed zero");
  expect_eq_u32(pingerElapsedUs(0, 0xFFFFFFF0UL), 16, "elapsed wrap");
  expect_eq_u32(pingerElapsedUs(50, 0xFFFFFFF0UL), 66, "elapsed wrap plus");

  const uint32_t pulse = 10000UL;
  const uint32_t period = 1000000UL;
  const uint32_t t0 = 1000UL;
  expect_true(pingerSchedule(false, true, t0 + pulse, t0, t0, pulse, period) == PINGER_SCHED_HOLD, "stopped holds");
  expect_true(pingerSchedule(true, true, t0, t0, t0, pulse, period) == PINGER_SCHED_HOLD, "burst just started");
  expect_true(pingerSchedule(true, true, t0 + pulse - 1UL, t0, t0, pulse, period) == PINGER_SCHED_HOLD, "one us early");
  expect_true(pingerSchedule(true, true, t0 + pulse, t0, t0, pulse, period) == PINGER_SCHED_END_BURST, "pulse end");
  expect_true(pingerSchedule(true, false, t0 + pulse, t0, t0, pulse, period) == PINGER_SCHED_HOLD, "wait after burst");
  expect_true(pingerSchedule(true, false, t0 + period - 1UL, t0, t0, pulse, period) == PINGER_SCHED_HOLD, "one us early period");
  expect_true(pingerSchedule(true, false, t0 + period, t0, t0, pulse, period) == PINGER_SCHED_BEGIN_BURST, "next burst");

  expect_true(pingerSchedule(true, true, 1000UL, 0, 0, 1000UL, period) == PINGER_SCHED_END_BURST, "1 ms pulse");
  expect_true(pingerSchedule(true, true, 99999UL, 0, 0, 100000UL, period) == PINGER_SCHED_HOLD, "100 ms early");
  expect_true(pingerSchedule(true, true, 100000UL, 0, 0, 100000UL, period) == PINGER_SCHED_END_BURST, "100 ms pulse");
  expect_true(pingerSchedule(true, false, 499999UL, 0, 0, pulse, 500000UL) == PINGER_SCHED_HOLD, "500 ms early");
  expect_true(pingerSchedule(true, false, 500000UL, 0, 0, pulse, 500000UL) == PINGER_SCHED_BEGIN_BURST, "500 ms period");
  expect_true(pingerSchedule(true, false, 1999999UL, 0, 0, pulse, 2000000UL) == PINGER_SCHED_HOLD, "2000 ms early");
  expect_true(pingerSchedule(true, false, 2000000UL, 0, 0, pulse, 2000000UL) == PINGER_SCHED_BEGIN_BURST, "2000 ms period");

  const uint32_t near_wrap = 0xFFFFF000UL;
  expect_true(pingerSchedule(true, true, near_wrap + 9999UL, near_wrap, near_wrap, pulse, period) == PINGER_SCHED_HOLD,
              "wrap pulse early");
  expect_true(pingerSchedule(true, true, near_wrap + pulse, near_wrap, near_wrap, pulse, period) == PINGER_SCHED_END_BURST,
              "wrap pulse end");
  const uint32_t cycle_wrap = 0xFFFFFFFFUL - 100UL;
  expect_true(pingerSchedule(true, false, cycle_wrap + 999999UL, cycle_wrap, cycle_wrap, pulse, period) == PINGER_SCHED_HOLD,
              "wrap period early");
  expect_true(pingerSchedule(true, false, cycle_wrap + period, cycle_wrap, cycle_wrap, pulse, period) == PINGER_SCHED_BEGIN_BURST,
              "wrap period");
  expect_true(pingerSchedule(true, true, 50UL, 0xFFFFFFF0UL, 0xFFFFFFF0UL, 100UL, period) == PINGER_SCHED_HOLD, "wrap still inside");
  expect_true(pingerSchedule(true, true, 50UL, 0xFFFFFFF0UL, 0xFFFFFFF0UL, 66UL, period) == PINGER_SCHED_END_BURST, "wrap exact elapsed");

  PingerSettings settings;
  pingerSettingsDefault(&settings);
  expect_true(pingerStart(&settings) == PINGER_APPLY_OK, "schedule start");
  expect_true(pingerSchedule(settings.running, true, 5000UL, 0, 0, 10000UL, 1000000UL) == PINGER_SCHED_HOLD, "running mid burst");
  expect_true(apply_line(&settings, "PULSE 1"), "shorten pulse");
  expect_true(pingerSchedule(settings.running, true, 5000UL, 0, 0, (uint32_t)settings.pulse_ms * 1000UL, 1000000UL) ==
                  PINGER_SCHED_END_BURST,
              "shorter pulse ends now");
  pingerStop(&settings);
  expect_true(pingerSchedule(settings.running, true, 5000UL, 0, 0, 1000UL, 1000000UL) == PINGER_SCHED_HOLD, "stop does not schedule end");
}

struct SectionResult {
  const char *name;
  int failed;
};

static SectionResult g_sections[8];
static int g_section_count = 0;
static int g_section_mark = 0;

static void begin_section() {
  g_section_mark = g_failures;
}

static void end_section(const char *name) {
  g_sections[g_section_count].name = name;
  g_sections[g_section_count].failed = g_failures - g_section_mark;
  g_section_count++;
}

static void write_report(const char *path, const char *when_run) {
  FILE *out = fopen(path, "w");
  if (out == nullptr) {
    printf("FAIL could not write %s\n", path);
    g_failures++;
    return;
  }
  fprintf(out, "# Pinger host verification\n\n");
  fprintf(out, "Run: %s\n\n", when_run);
  fprintf(out, "This file is generated by `arduino_pinger/test_pinger_logic.cpp`. ");
  fprintf(out, "Every PASS/FAIL below is from that run. ");
  fprintf(out, "Calculated Timer1 frequencies are arithmetic at 16 MHz. ");
  fprintf(out, "They are not scope readings, pin measurements, jitter captures, or acoustic results.\n\n");
  fprintf(out, "## Logic results\n\n");
  fprintf(out, "| Check | Result | Failures |\n| --- | --- | ---: |\n");
  for (int i = 0; i < g_section_count; i++) {
    fprintf(out, "| %s | %s | %d |\n", g_sections[i].name, g_sections[i].failed == 0 ? "PASS" : "FAIL", g_sections[i].failed);
  }
  fprintf(out, "\nTotal assertion failures: %d\n\n", g_failures);
  if (g_failures > 0) {
    fprintf(out, "Failed checks:\n\n");
    int shown = g_failures < kFailCap ? g_failures : kFailCap;
    for (int i = 0; i < shown; i++) {
      fprintf(out, "- %s\n", g_fail_names[i]);
    }
    fprintf(out, "\n");
  }

  fprintf(out, "## Carrier frequency table\n\n");
  fprintf(out, "Each supported `FREQ` step. `OCR1A` is the value the sketch loads. ");
  fprintf(out, "Timer Hz is `F_CPU / (2 * (1 + OCR1A))` with the fraction truncated to 4 digits, ");
  fprintf(out, "the same direction as the serial print (hundredths, also truncated). ");
  fprintf(out, "Error is `(timer - requested) / requested`, rounded to 0.0001%%. ");
  fprintf(out, "No acoustic tolerance is applied. A row PASSes when the step is accepted and the printed frequency matches that division.\n\n");
  fprintf(out, "| Requested Hz | OCR1A | Timer Hz | Printed Hz | Error vs request | Logic |\n");
  fprintf(out, "| ---: | ---: | ---: | ---: | ---: | --- |\n");
  for (int i = 0; i < g_freq_count; i++) {
    FreqRow *row = &g_freq_rows[i];
    char error[24];
    format_percent(error, sizeof(error), row->error_e4);
    fprintf(out, "| %u | %u | %lu.%04lu | %lu.%02u | %s | %s |\n", (unsigned)row->requested, (unsigned)row->ocr,
            (unsigned long)row->hz, (unsigned long)row->frac4, (unsigned long)row->hz, (unsigned)row->hundredths, error,
            row->pass ? "PASS" : "FAIL");
  }
  if (g_freq_count > 0) {
    FreqRow *worst = &g_freq_rows[g_freq_worst_index];
    char error[24];
    format_percent(error, sizeof(error), worst->error_e4);
    fprintf(out, "\nLargest absolute divider error on this grid: %u Hz requested, timer %lu.%04lu Hz, error %s.\n",
            (unsigned)worst->requested, (unsigned long)worst->hz, (unsigned long)worst->frac4, error);
  }

  fprintf(out, "\n## Not measured on hardware\n\n");
  fprintf(out, "| Check | Result | Why |\n| --- | --- | --- |\n");
  fprintf(out, "| Uno compile | see the compile section | Filled by the verification script when Arduino CLI runs |\n");
  fprintf(out, "| Timer1 pin toggle on D9 | NOT RUN | Needs a board and a scope or counter |\n");
  fprintf(out, "| D8 / D9 idle and burst levels | NOT RUN | Needs a board |\n");
  fprintf(out, "| Burst width, repetition, and serial jitter | NOT RUN | Host time is a mocked `uint32_t`, not `micros()` on an Uno |\n");
  fprintf(out, "| STOP pin latency | NOT RUN | Host test clears the running flag only |\n");
  fprintf(out, "| Boot / reset high-Z | NOT RUN | Happens before `setup()` |\n");
  fprintf(out, "| Acoustic level, waveform, or range | NOT RUN | No amplifier, transducer, or hydrophone is connected |\n");

  fprintf(out, "\n## Commands to rerun\n\n");
  fprintf(out, "From the repository root:\n\n");
  fprintf(out, "```powershell\n");
  fprintf(out, "powershell -ExecutionPolicy Bypass -File arduino_pinger\\run_host_verification.ps1\n");
  fprintf(out, "```\n\n");
  fprintf(out, "Host tests only, if `g++` is on PATH:\n\n");
  fprintf(out, "```powershell\n");
  fprintf(out, "g++ -std=c++11 -Wall -Wextra -I arduino_pinger -o $env:TEMP\\test_pinger_logic.exe arduino_pinger\\test_pinger_logic.cpp\n");
  fprintf(out, "& $env:TEMP\\test_pinger_logic.exe arduino_pinger\\HOST_VERIFICATION.md\n");
  fprintf(out, "```\n\n");
  fprintf(out, "Firmware build, if `arduino-cli` is on PATH:\n\n");
  fprintf(out, "```powershell\n");
  fprintf(out, "arduino-cli compile --warnings all --fqbn arduino:avr:uno arduino_pinger/robosub_pinger\n");
  fprintf(out, "```\n\n");
  fprintf(out, "If the CLI is missing, install [Arduino IDE 2](https://www.arduino.cc/en/software) or the standalone Arduino CLI, then:\n\n");
  fprintf(out, "```powershell\n");
  fprintf(out, "arduino-cli core update-index\n");
  fprintf(out, "arduino-cli core install arduino:avr\n");
  fprintf(out, "arduino-cli compile --warnings all --fqbn arduino:avr:uno arduino_pinger/robosub_pinger\n");
  fprintf(out, "```\n\n");
  fprintf(out, "Arduino IDE 2 also ships a CLI that is often not on PATH:\n\n");
  fprintf(out, "`%%LOCALAPPDATA%%\\Programs\\Arduino IDE\\resources\\app\\lib\\backend\\resources\\arduino-cli.exe`\n");

  fprintf(out, "\n## Physical checklist\n\n");
  fprintf(out, "Do these only with an Uno or classic Nano on the bench. Leave the amplifier and transducer disconnected. ");
  fprintf(out, "Procedure detail is in `arduino_pinger/TEST_PLAN.md`. None of these were run for this report.\n\n");
  fprintf(out, "| Step | Result |\n| --- | --- |\n");
  fprintf(out, "| Upload the sketch. Confirm D8 and D9 are LOW after `setup()`, and note any high-Z interval during reset. | NOT RUN |\n");
  fprintf(out, "| Fit a pull-down on D8 before a driver is attached. | NOT RUN |\n");
  fprintf(out, "| Serial at 115200. `STATUS`, `STOP`, `START`, `STOP`. Carrier only while started; `STOP` forces both pins LOW. | NOT RUN |\n");
  fprintf(out, "| Scope D9 at 25000, 30000, 35000, and 40000 Hz against the printed actual frequency, not the nominal request. | NOT RUN |\n");
  fprintf(out, "| Scope D8 high time and repetition at the default 10 ms / 1000 ms, then at 1 ms / 500 ms and 100 ms / 2000 ms. | NOT RUN |\n");
  fprintf(out, "| Reject `FREQ -30000`, `FREQ 30250`, `PERIOD 499`, and `PULSE 101` on the board. | NOT RUN |\n");
  fprintf(out, "| Measure burst stretch while `HELP` or `STATUS` is printing. | NOT RUN |\n");
  fprintf(out, "| Run `START` for more than 72 minutes and confirm bursts continue across the `micros()` wrap. | NOT RUN |\n");
  fprintf(out, "| Acoustic check with a real projector and a receive hydrophone. | NOT RUN |\n");

  fprintf(out, "\n## Firmware compile\n\n");
  fprintf(out, "<!-- BEGIN_COMPILE -->\n");
  fprintf(out, "Result: NOT RUN\n\n");
  fprintf(out, "The host executable does not invoke Arduino CLI. `run_host_verification.ps1` replaces this section after a compile attempt.\n");
  fprintf(out, "<!-- END_COMPILE -->\n");
  fclose(out);
}

int main(int argc, char **argv) {
  const char *report_path = argc > 1 ? argv[1] : "arduino_pinger/HOST_VERIFICATION.md";
  const char *when_run = argc > 2 ? argv[2] : "unspecified";

  begin_section();
  test_anchor_frequencies();
  end_section("Anchor OCR values (25, 30, 35, 40 kHz)");

  begin_section();
  test_rounding_is_nearest();
  end_section("Nearest divider on every 500 Hz step");

  begin_section();
  test_numbers();
  end_section("Integer parsing, signs, overflow, trailing junk");

  begin_section();
  test_lines();
  end_section("Existing command samples");

  begin_section();
  test_limits_and_state();
  end_section("Limits and START/STOP state");

  begin_section();
  test_frequency_grid();
  end_section("Full carrier grid, printed Hz, and percent error");

  begin_section();
  test_more_commands();
  end_section("Additional valid and rejected serial commands");

  begin_section();
  test_schedule_and_rollover();
  end_section("Burst schedule and mocked micros() rollover");

  write_report(report_path, when_run);
  if (g_failures != 0) {
    printf("%d failed\n", g_failures);
    return 1;
  }
  printf("ok\n");
  return 0;
}
