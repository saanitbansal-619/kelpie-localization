/*
  RoboSub logic-level acoustic pinger controller.

  Board: Arduino Uno R3 or classic Nano, ATmega328P, 16 MHz.
  D9 (PB1 / OC1A): Timer1 square-wave carrier, for an external driver input.
  D8 (PB0): driver enable. LOW when idle. HIGH only during a burst.
  This sketch does not power a transducer. D9 is a 0–5 V logic output.

  Timer1 is used in CTC mode with TOP = OCR1A and OC1A set to toggle.
  ATmega328P datasheet, Clear Timer on Compare Match:
    f_OC1A = F_CPU / (2 * N * (1 + OCR1A))
  N = 1. OCR1A is chosen by rounding that divider to the nearest integer.
  In CTC mode OCR1A is not buffered. It is updated only while the timer
  clock is stopped, because a live write can leave TCNT1 above the new
  TOP and the counter will then run out to 0xFFFF before the next match.

  digitalWrite(9) is never used after setup. The Arduino core's
  digitalWrite() calls turnOffPWM() and clears COM1A, which would kill
  the carrier.

  TEST_MODE only adds a serial warning. It does not mute D8 or D9, does
  not block START, and does not disable an external amplifier. From reset
  until setup() runs, both pins are high-Z. A pull-down on D8 is required
  hardware; this sketch cannot hold the driver off during that window.
*/

#if F_CPU != 16000000L
#error This firmware requires a 16 MHz ATmega328P (Arduino Uno or classic Nano).
#endif

#include <Arduino.h>
#include <string.h>

#include "pinger_logic.h"

#define TEST_MODE 0

static const uint32_t SERIAL_BAUD = 115200UL;
static const uint8_t LINE_MAX = 48;

static const uint8_t PIN_ENABLE = 8;   // PB0
static const uint8_t PIN_CARRIER = 9;  // PB1 / OC1A

static PingerSettings g_settings;
static bool g_in_burst = false;
static uint16_t g_burst_freq_hz = PINGER_FREQ_DEFAULT_HZ;
static uint32_t g_cycle_start_us = 0;
static uint32_t g_burst_start_us = 0;

static char g_rx[LINE_MAX];
static uint8_t g_rx_len = 0;
static bool g_rx_overflow = false;
static char g_pending[LINE_MAX];
static bool g_pending_ready = false;
static bool g_pending_overflow = false;
static char g_stashed[LINE_MAX];
static bool g_stashed_ready = false;
static bool g_stashed_overflow = false;
static bool g_in_handler = false;

static uint32_t periodUs() {
  return (uint32_t)g_settings.period_ms * 1000UL;
}

static uint32_t pulseUs() {
  return (uint32_t)g_settings.pulse_ms * 1000UL;
}

static void printHz(uint16_t freq_hz) {
  uint16_t ocr = pingerOcrForFrequency(F_CPU, freq_hz);
  uint32_t hz = 0;
  uint8_t frac = 0;
  pingerActualFrequency(F_CPU, ocr, &hz, &frac);
  Serial.print(hz);
  Serial.print('.');
  if (frac < 10) {
    Serial.print('0');
  }
  Serial.print(frac);
  Serial.print(F(" Hz (OCR1A "));
  Serial.print(ocr);
  Serial.print(')');
}

static void outputIdle() {
  uint8_t old_sreg = SREG;
  cli();
  // Stop the clock before touching TOP. A running CTC counter treats OCR1A
  // as an immediate compare value, not a buffered PWM register.
  TCCR1B = 0;
  TCCR1A = 0;
  TCNT1 = 0;
  // Write-1-to-clear. Leave Timer0 flags alone so millis()/micros() survive.
  TIFR1 = _BV(OCF1A) | _BV(TOV1);
  PORTB &= ~_BV(PB1);
  PORTB &= ~_BV(PB0);
  SREG = old_sreg;
  g_in_burst = false;
}

static void burstBegin() {
  uint16_t ocr = pingerOcrForFrequency(F_CPU, g_settings.freq_hz);
  g_burst_freq_hz = g_settings.freq_hz;

  uint8_t old_sreg = SREG;
  cli();
  TCCR1B = 0;
  TCCR1A = 0;
  PORTB &= ~_BV(PB1);
  TCNT1 = 0;
  OCR1A = ocr;
  TIFR1 = _BV(OCF1A) | _BV(TOV1);
  // Toggle is armed while the clock is still stopped, so the pin stays low
  // until the first compare match. The first half-cycle is therefore low.
  TCCR1A = _BV(COM1A0);
  PORTB |= _BV(PB0);
  TCCR1B = _BV(WGM12) | _BV(CS10);
  g_burst_start_us = micros();
  SREG = old_sreg;
  g_in_burst = true;
}

static void servicePinger() {
  if (!g_settings.running) {
    return;
  }

  PingerScheduleAction action = pingerSchedule(true, g_in_burst, micros(), g_burst_start_us,
                                               g_cycle_start_us, pulseUs(), periodUs());
  if (action == PINGER_SCHED_END_BURST) {
    outputIdle();
  } else if (action == PINGER_SCHED_BEGIN_BURST) {
    burstBegin();
    g_cycle_start_us = g_burst_start_us;
  }
}

// Called between serial lines so a burst can end during a multi-line reply.
// One Serial.println can still stretch the burst by that line's TX time
// (a few milliseconds at 115200). STOP itself is applied in outputIdle()
// before its own "OK" text is printed, but only after the line is parsed.
static void absorbSerial();

static void replyLine(const __FlashStringHelper *message) {
  servicePinger();
  Serial.println(message);
  servicePinger();
  // Pick up a STOP that arrived while this line was shifting out.
  absorbSerial();
}

static void printHelp() {
  replyLine(F("Commands:"));
  replyLine(F("  HELP"));
  replyLine(F("  STATUS"));
  replyLine(F("  FREQ <Hz>     25000 to 40000, steps of 500"));
  replyLine(F("  PERIOD <ms>   500 to 2000"));
  replyLine(F("  PULSE <ms>    1 to 100, must be < PERIOD"));
  replyLine(F("  START"));
  replyLine(F("  STOP"));
  replyLine(F("  TEST          bench notes only; does not mute D8 or D9"));
  replyLine(F("D9 is a logic square wave for an external driver, not a transducer."));
}

static void printTestNotes() {
  replyLine(F("TEST does not start, stop, or mute the carrier."));
  replyLine(F("START drives D9 and D8 whether TEST_MODE is 0 or 1."));
  replyLine(F("TEST_MODE does not disable an external amplifier."));
  replyLine(F("From reset until setup(), D8 and D9 are high-Z."));
  replyLine(F("Fit a pull-down on D8 so a driver stays disabled in that window."));
  servicePinger();
  Serial.print(F("Requested "));
  Serial.print(g_settings.freq_hz);
  Serial.print(F(" Hz, timer produces "));
  printHz(g_settings.freq_hz);
  Serial.println();
  servicePinger();
  absorbSerial();
  replyLine(F("A 50% logic square wave has odd harmonics. Acoustic output is TBD."));
#if TEST_MODE
  replyLine(F("TEST_MODE compile flag is 1 (warning only)."));
#else
  replyLine(F("TEST_MODE compile flag is 0 (warning only when set to 1)."));
#endif
}

static void printStatus() {
  servicePinger();
  Serial.print(F("STATE "));
  Serial.println(g_settings.running ? F("running") : F("stopped"));
  servicePinger();
  absorbSerial();
  Serial.print(F("BURST "));
  Serial.println(g_in_burst ? F("on") : F("off"));
  servicePinger();
  absorbSerial();
  Serial.print(F("FREQ requested "));
  Serial.print(g_settings.freq_hz);
  Serial.print(F(" Hz, actual "));
  printHz(g_settings.freq_hz);
  Serial.println();
  servicePinger();
  absorbSerial();
  if (g_in_burst) {
    Serial.print(F("FREQ generating "));
    Serial.print(g_burst_freq_hz);
    Serial.print(F(" Hz, actual "));
    printHz(g_burst_freq_hz);
    Serial.println();
    servicePinger();
    absorbSerial();
  }
  Serial.print(F("PERIOD "));
  Serial.print(g_settings.period_ms);
  Serial.println(F(" ms"));
  servicePinger();
  absorbSerial();
  Serial.print(F("PULSE "));
  Serial.print(g_settings.pulse_ms);
  Serial.println(F(" ms"));
  servicePinger();
  absorbSerial();
  replyLine(F("PINS D9 carrier OC1A, D8 enable, idle level LOW"));
  replyLine(F("NOTE 5 V GPIO cannot drive a transducer. External driver is TBD."));
  replyLine(F("NOTE STOP latency is the time until this command is parsed, then pins go LOW before OK is printed."));
}

static void reportNumberError(PingerNumberStatus status, const __FlashStringHelper *example) {
  if (status == PINGER_NUM_SIGN) {
    replyLine(F("ERR sign is not allowed"));
    return;
  }
  if (status == PINGER_NUM_OVERFLOW) {
    replyLine(F("ERR number does not fit in 0..65535"));
    return;
  }
  if (status == PINGER_NUM_EMPTY || status == PINGER_NUM_MALFORMED) {
    replyLine(example);
  }
}

static void executeStop() {
  pingerStop(&g_settings);
  outputIdle();
  // Pins are already LOW. The following print does not gate the pin update.
  Serial.println(F("OK STOP pins LOW"));
  servicePinger();
}

static bool pendingIsStop(const char *line) {
  char copy[LINE_MAX];
  strncpy(copy, line, LINE_MAX - 1);
  copy[LINE_MAX - 1] = '\0';
  PingerLine parsed = pingerParseLine(copy);
  return parsed.command == PINGER_CMD_STOP && !parsed.extra;
}

static void handleLine(char *line) {
  servicePinger();
  PingerLine parsed = pingerParseLine(line);
  if (parsed.command == PINGER_CMD_EMPTY) {
    return;
  }
  if (parsed.command == PINGER_CMD_UNKNOWN) {
    replyLine(F("ERR unknown command; send HELP"));
    return;
  }
  if (parsed.extra) {
    replyLine(F("ERR unexpected argument"));
    return;
  }

  if (parsed.command == PINGER_CMD_HELP) {
    printHelp();
    return;
  }
  if (parsed.command == PINGER_CMD_STATUS) {
    printStatus();
    return;
  }
  if (parsed.command == PINGER_CMD_TEST) {
    printTestNotes();
    return;
  }
  if (parsed.command == PINGER_CMD_START) {
    if (pingerStart(&g_settings) == PINGER_APPLY_ALREADY_RUNNING) {
      replyLine(F("ERR already running; send STOP first"));
      return;
    }
    burstBegin();
    g_cycle_start_us = g_burst_start_us;
    servicePinger();
    Serial.print(F("OK START actual "));
    printHz(g_burst_freq_hz);
    Serial.println();
    servicePinger();
    absorbSerial();
    return;
  }
  if (parsed.command == PINGER_CMD_STOP) {
    executeStop();
    return;
  }

  if (parsed.number != PINGER_NUM_OK) {
    if (parsed.command == PINGER_CMD_FREQ) {
      reportNumberError(parsed.number, F("ERR FREQ <Hz>, example FREQ 30000"));
    } else if (parsed.command == PINGER_CMD_PERIOD) {
      reportNumberError(parsed.number, F("ERR PERIOD <ms>, example PERIOD 1000"));
    } else {
      reportNumberError(parsed.number, F("ERR PULSE <ms>, example PULSE 10"));
    }
    return;
  }

  if (parsed.command == PINGER_CMD_FREQ) {
    if (pingerSetFreq(&g_settings, parsed.value) != PINGER_APPLY_OK) {
      replyLine(F("ERR frequency must be 25000 to 40000 Hz in 500 Hz steps"));
      return;
    }
    servicePinger();
    Serial.print(F("OK FREQ actual "));
    printHz(g_settings.freq_hz);
    if (g_in_burst && g_burst_freq_hz != g_settings.freq_hz) {
      Serial.print(F("; applies on next burst"));
    }
    Serial.println();
    servicePinger();
    absorbSerial();
    return;
  }
  if (parsed.command == PINGER_CMD_PERIOD) {
    PingerApplyStatus status = pingerSetPeriod(&g_settings, parsed.value);
    if (status == PINGER_APPLY_NOT_SHORTER) {
      replyLine(F("ERR period must be greater than the current pulse width"));
      return;
    }
    if (status != PINGER_APPLY_OK) {
      replyLine(F("ERR period must be 500 to 2000 ms"));
      return;
    }
    servicePinger();
    Serial.print(F("OK PERIOD "));
    Serial.print(g_settings.period_ms);
    Serial.println(F(" ms"));
    servicePinger();
    absorbSerial();
    return;
  }
  if (parsed.command == PINGER_CMD_PULSE) {
    PingerApplyStatus status = pingerSetPulse(&g_settings, parsed.value);
    if (status == PINGER_APPLY_NOT_SHORTER) {
      replyLine(F("ERR pulse must be shorter than the repetition period"));
      return;
    }
    if (status != PINGER_APPLY_OK) {
      replyLine(F("ERR pulse must be 1 to 100 ms"));
      return;
    }
    servicePinger();
    Serial.print(F("OK PULSE "));
    Serial.print(g_settings.pulse_ms);
    Serial.println(F(" ms"));
    servicePinger();
    absorbSerial();
  }
}

static bool enqueueRx(bool overflow) {
  char *dest = nullptr;
  bool *ready = nullptr;
  bool *overflow_flag = nullptr;
  if (!g_pending_ready) {
    dest = g_pending;
    ready = &g_pending_ready;
    overflow_flag = &g_pending_overflow;
  } else if (!g_stashed_ready) {
    dest = g_stashed;
    ready = &g_stashed_ready;
    overflow_flag = &g_stashed_overflow;
  } else {
    return false;
  }
  *overflow_flag = overflow;
  if (!overflow) {
    memcpy(dest, g_rx, g_rx_len);
    dest[g_rx_len] = '\0';
  }
  *ready = true;
  return true;
}

static void promoteStash() {
  if (g_pending_ready || !g_stashed_ready) {
    return;
  }
  memcpy(g_pending, g_stashed, LINE_MAX);
  g_pending_overflow = g_stashed_overflow;
  g_pending_ready = true;
  g_stashed_ready = false;
}

static void absorbSerial() {
  // Keep reading while a reply is printing. STOP is applied immediately.
  // One other command can sit in g_pending and one in g_stashed; further
  // bytes stay in the UART until a slot frees.
  while (Serial.available() > 0 && !(g_pending_ready && g_stashed_ready)) {
    int raw = Serial.read();
    if (raw < 0) {
      return;
    }
    char ch = (char)raw;
    if (ch == '\r' || ch == '\n') {
      servicePinger();
      if (g_rx_overflow) {
        enqueueRx(true);
      } else if (g_rx_len > 0) {
        g_rx[g_rx_len] = '\0';
        if (g_in_handler && pendingIsStop(g_rx)) {
          executeStop();
        } else {
          enqueueRx(false);
        }
      }
      g_rx_len = 0;
      g_rx_overflow = false;
      continue;
    }
    if (g_rx_overflow) {
      continue;
    }
    if (g_rx_len + 1 >= LINE_MAX) {
      g_rx_overflow = true;
      g_rx_len = 0;
      continue;
    }
    g_rx[g_rx_len++] = ch;
  }
}

void setup() {
  pingerSettingsDefault(&g_settings);
  // Direction and idle level before Serial.begin, which can block on some hosts.
  // This does not cover the reset/bootloader window. D8 needs a hardware pull-down.
  pinMode(PIN_ENABLE, OUTPUT);
  pinMode(PIN_CARRIER, OUTPUT);
  TIMSK1 = 0;
  outputIdle();

  Serial.begin(SERIAL_BAUD);
#if TEST_MODE
  Serial.println(F("TEST_MODE 1 is a warning only. START still drives D8 and D9. It does not disable an amplifier."));
#endif
  Serial.println(F("RoboSub pinger idle. Pins LOW until START. Send HELP."));
  Serial.print(F("Defaults: "));
  Serial.print(g_settings.freq_hz);
  Serial.print(F(" Hz requested, actual "));
  printHz(g_settings.freq_hz);
  Serial.print(F(", period "));
  Serial.print(g_settings.period_ms);
  Serial.print(F(" ms, pulse "));
  Serial.print(g_settings.pulse_ms);
  Serial.println(F(" ms"));
}

void loop() {
  servicePinger();
  promoteStash();
  absorbSerial();
  if (!g_pending_ready) {
    return;
  }
  g_pending_ready = false;
  if (g_pending_overflow) {
    g_pending_overflow = false;
    replyLine(F("ERR line too long"));
    return;
  }
  g_in_handler = true;
  handleLine(g_pending);
  g_in_handler = false;
}
