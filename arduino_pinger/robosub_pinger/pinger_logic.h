// Pure pinger decisions: frequency rounding, number checks, and settings.
// No pins, timers, or serial I/O. The sketch and the host test both use this.

#ifndef PINGER_LOGIC_H
#define PINGER_LOGIC_H

#include <stdint.h>
#include <string.h>

static const uint32_t PINGER_F_CPU_HZ = 16000000UL;
static const uint16_t PINGER_FREQ_MIN_HZ = 25000;
static const uint16_t PINGER_FREQ_MAX_HZ = 40000;
static const uint16_t PINGER_FREQ_STEP_HZ = 500;
static const uint16_t PINGER_FREQ_DEFAULT_HZ = 30000;
static const uint16_t PINGER_PERIOD_MIN_MS = 500;
static const uint16_t PINGER_PERIOD_MAX_MS = 2000;
static const uint16_t PINGER_PERIOD_DEFAULT_MS = 1000;
static const uint16_t PINGER_PULSE_MIN_MS = 1;
static const uint16_t PINGER_PULSE_MAX_MS = 100;
static const uint16_t PINGER_PULSE_DEFAULT_MS = 10;

enum PingerNumberStatus {
  PINGER_NUM_OK = 0,
  PINGER_NUM_EMPTY,
  PINGER_NUM_SIGN,
  PINGER_NUM_MALFORMED,
  PINGER_NUM_OVERFLOW
};

enum PingerCommand {
  PINGER_CMD_EMPTY = 0,
  PINGER_CMD_HELP,
  PINGER_CMD_STATUS,
  PINGER_CMD_TEST,
  PINGER_CMD_START,
  PINGER_CMD_STOP,
  PINGER_CMD_FREQ,
  PINGER_CMD_PERIOD,
  PINGER_CMD_PULSE,
  PINGER_CMD_UNKNOWN
};

enum PingerApplyStatus {
  PINGER_APPLY_OK = 0,
  PINGER_APPLY_FREQ,
  PINGER_APPLY_PERIOD,
  PINGER_APPLY_PULSE,
  PINGER_APPLY_NOT_SHORTER,
  PINGER_APPLY_EXTRA,
  PINGER_APPLY_ALREADY_RUNNING
};

struct PingerSettings {
  uint16_t freq_hz;
  uint16_t period_ms;
  uint16_t pulse_ms;
  bool running;
};

struct PingerLine {
  PingerCommand command;
  PingerNumberStatus number;
  uint16_t value;
  bool extra;
};

// ticks = OCR1A + 1 = nearest integer to F_CPU / (2 * f).
// (F_CPU + f) / (2 * f) is floor(F_CPU / (2 * f) + 1/2); an exact half rounds up.
inline uint16_t pingerOcrForFrequency(uint32_t f_cpu, uint16_t freq_hz) {
  uint32_t ticks = (f_cpu + (uint32_t)freq_hz) / (2UL * (uint32_t)freq_hz);
  if (ticks < 1UL) {
    ticks = 1UL;
  }
  return (uint16_t)(ticks - 1UL);
}

// Hundredths are truncated, matching the serial print.
inline void pingerActualFrequency(uint32_t f_cpu, uint16_t ocr, uint32_t *hz, uint8_t *hundredths) {
  uint32_t den = 2UL * ((uint32_t)ocr + 1UL);
  *hz = f_cpu / den;
  *hundredths = (uint8_t)(((f_cpu % den) * 100UL) / den);
}

// Digits only. Rejects '+', '-', empty text, trailing junk, and values above 65535.
inline PingerNumberStatus pingerParseU16(const char *text, uint16_t *value) {
  if (text == nullptr || text[0] == '\0') {
    return PINGER_NUM_EMPTY;
  }
  if (text[0] == '+' || text[0] == '-') {
    return PINGER_NUM_SIGN;
  }
  if (text[0] < '0' || text[0] > '9') {
    return PINGER_NUM_MALFORMED;
  }
  uint32_t acc = 0;
  const char *cursor = text;
  while (*cursor >= '0' && *cursor <= '9') {
    uint32_t digit = (uint32_t)(*cursor - '0');
    if (acc > 6553UL || (acc == 6553UL && digit > 5UL)) {
      return PINGER_NUM_OVERFLOW;
    }
    acc = acc * 10UL + digit;
    cursor++;
  }
  while (*cursor == ' ' || *cursor == '\t') {
    cursor++;
  }
  if (*cursor != '\0') {
    return PINGER_NUM_MALFORMED;
  }
  *value = (uint16_t)acc;
  return PINGER_NUM_OK;
}

inline void pingerSettingsDefault(PingerSettings *settings) {
  settings->freq_hz = PINGER_FREQ_DEFAULT_HZ;
  settings->period_ms = PINGER_PERIOD_DEFAULT_MS;
  settings->pulse_ms = PINGER_PULSE_DEFAULT_MS;
  settings->running = false;
}

inline PingerApplyStatus pingerSetFreq(PingerSettings *settings, uint16_t freq_hz) {
  if (freq_hz < PINGER_FREQ_MIN_HZ || freq_hz > PINGER_FREQ_MAX_HZ ||
      (freq_hz % PINGER_FREQ_STEP_HZ) != 0) {
    return PINGER_APPLY_FREQ;
  }
  settings->freq_hz = freq_hz;
  return PINGER_APPLY_OK;
}

inline PingerApplyStatus pingerSetPeriod(PingerSettings *settings, uint16_t period_ms) {
  if (period_ms < PINGER_PERIOD_MIN_MS || period_ms > PINGER_PERIOD_MAX_MS) {
    return PINGER_APPLY_PERIOD;
  }
  if (settings->pulse_ms >= period_ms) {
    return PINGER_APPLY_NOT_SHORTER;
  }
  settings->period_ms = period_ms;
  return PINGER_APPLY_OK;
}

inline PingerApplyStatus pingerSetPulse(PingerSettings *settings, uint16_t pulse_ms) {
  if (pulse_ms < PINGER_PULSE_MIN_MS || pulse_ms > PINGER_PULSE_MAX_MS) {
    return PINGER_APPLY_PULSE;
  }
  if (pulse_ms >= settings->period_ms) {
    return PINGER_APPLY_NOT_SHORTER;
  }
  settings->pulse_ms = pulse_ms;
  return PINGER_APPLY_OK;
}

inline PingerApplyStatus pingerStart(PingerSettings *settings) {
  if (settings->running) {
    return PINGER_APPLY_ALREADY_RUNNING;
  }
  settings->running = true;
  return PINGER_APPLY_OK;
}

inline void pingerStop(PingerSettings *settings) {
  settings->running = false;
}

enum PingerScheduleAction {
  PINGER_SCHED_HOLD = 0,
  PINGER_SCHED_END_BURST,
  PINGER_SCHED_BEGIN_BURST
};

// Unsigned subtraction. Correct across the micros() wrap (~71.6 min) when the
// true gap is shorter than 2^32 µs. Burst and period gaps are at most 2 s.
inline uint32_t pingerElapsedUs(uint32_t now_us, uint32_t start_us) {
  return now_us - start_us;
}

// Decision used by servicePinger. Does not sample micros(), touch pins, or
// program Timer1. STOP still has to drive the pins idle itself: a cleared
// running flag only makes later calls hold.
inline PingerScheduleAction pingerSchedule(bool running, bool in_burst, uint32_t now_us,
                                           uint32_t burst_start_us, uint32_t cycle_start_us,
                                           uint32_t pulse_us, uint32_t period_us) {
  if (!running) {
    return PINGER_SCHED_HOLD;
  }
  if (in_burst) {
    if (pingerElapsedUs(now_us, burst_start_us) >= pulse_us) {
      return PINGER_SCHED_END_BURST;
    }
    return PINGER_SCHED_HOLD;
  }
  if (pingerElapsedUs(now_us, cycle_start_us) >= period_us) {
    return PINGER_SCHED_BEGIN_BURST;
  }
  return PINGER_SCHED_HOLD;
}

inline bool pingerIsSpace(char ch) {
  return ch == ' ' || ch == '\t';
}

inline PingerCommand pingerCommandFromToken(const char *token) {
  if (strcmp(token, "HELP") == 0) return PINGER_CMD_HELP;
  if (strcmp(token, "STATUS") == 0) return PINGER_CMD_STATUS;
  if (strcmp(token, "TEST") == 0) return PINGER_CMD_TEST;
  if (strcmp(token, "START") == 0) return PINGER_CMD_START;
  if (strcmp(token, "STOP") == 0) return PINGER_CMD_STOP;
  if (strcmp(token, "FREQ") == 0) return PINGER_CMD_FREQ;
  if (strcmp(token, "PERIOD") == 0) return PINGER_CMD_PERIOD;
  if (strcmp(token, "PULSE") == 0) return PINGER_CMD_PULSE;
  return PINGER_CMD_UNKNOWN;
}

// Uppercases the command token in place and splits once on space or tab.
inline PingerLine pingerParseLine(char *line) {
  PingerLine parsed;
  parsed.command = PINGER_CMD_EMPTY;
  parsed.number = PINGER_NUM_OK;
  parsed.value = 0;
  parsed.extra = false;

  while (pingerIsSpace(*line)) {
    line++;
  }
  if (*line == '\0') {
    return parsed;
  }

  char *arg = line;
  while (*arg != '\0' && !pingerIsSpace(*arg)) {
    if (*arg >= 'a' && *arg <= 'z') {
      *arg = (char)(*arg - ('a' - 'A'));
    }
    arg++;
  }
  if (*arg != '\0') {
    *arg = '\0';
    arg++;
    while (pingerIsSpace(*arg)) {
      arg++;
    }
  }

  parsed.command = pingerCommandFromToken(line);
  bool takes_number = parsed.command == PINGER_CMD_FREQ || parsed.command == PINGER_CMD_PERIOD ||
                      parsed.command == PINGER_CMD_PULSE;
  if (!takes_number) {
    if (parsed.command != PINGER_CMD_UNKNOWN && parsed.command != PINGER_CMD_EMPTY) {
      parsed.extra = (*arg != '\0');
    }
    return parsed;
  }
  parsed.number = pingerParseU16(arg, &parsed.value);
  return parsed;
}

#endif
