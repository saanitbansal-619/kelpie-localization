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

  Set TEST_MODE to 1 before a bench-scope session with no transducer and
  no power amplifier connected. The pins behave the same either way.
*/

#if F_CPU != 16000000L
#error This firmware requires a 16 MHz ATmega328P (Arduino Uno or classic Nano).
#endif

#include <Arduino.h>
#include <stdlib.h>
#include <string.h>

#define TEST_MODE 0

static const uint32_t SERIAL_BAUD = 115200UL;
static const uint16_t FREQ_MIN_HZ = 25000;
static const uint16_t FREQ_MAX_HZ = 40000;
static const uint16_t FREQ_STEP_HZ = 500;
static const uint16_t FREQ_DEFAULT_HZ = 30000;
static const uint16_t PERIOD_MIN_MS = 500;
static const uint16_t PERIOD_MAX_MS = 2000;
static const uint16_t PERIOD_DEFAULT_MS = 1000;
static const uint16_t PULSE_MIN_MS = 1;
static const uint16_t PULSE_MAX_MS = 100;
static const uint16_t PULSE_DEFAULT_MS = 10;
static const uint8_t LINE_MAX = 48;

static const uint8_t PIN_ENABLE = 8;    // PB0
static const uint8_t PIN_CARRIER = 9;   // PB1 / OC1A

static uint16_t g_freq_hz = FREQ_DEFAULT_HZ;
static uint16_t g_period_ms = PERIOD_DEFAULT_MS;
static uint16_t g_pulse_ms = PULSE_DEFAULT_MS;
static uint32_t g_period_us = (uint32_t)PERIOD_DEFAULT_MS * 1000UL;
static uint32_t g_pulse_us = (uint32_t)PULSE_DEFAULT_MS * 1000UL;

static bool g_running = false;
static bool g_in_burst = false;
static uint16_t g_burst_freq_hz = FREQ_DEFAULT_HZ;
static uint16_t g_loaded_ocr = 0;
static uint32_t g_cycle_start_us = 0;
static uint32_t g_burst_start_us = 0;

static char g_line[LINE_MAX];
static uint8_t g_line_len = 0;
static bool g_line_overflow = false;

// Nearest divider for f = F_CPU / (2 * ticks), ticks = OCR1A + 1.
// (F_CPU + f) / (2 * f) is floor(F_CPU / (2 * f) + 1/2), so halves round up.
static uint16_t ocrForFrequency(uint16_t freq_hz) {
  uint32_t ticks = (F_CPU + (uint32_t)freq_hz) / (2UL * (uint32_t)freq_hz);
  if (ticks < 1UL) {
    ticks = 1UL;
  }
  return (uint16_t)(ticks - 1UL);
}

static void actualFrequency(uint16_t ocr, uint32_t &hz, uint8_t &hundredths) {
  uint32_t den = 2UL * ((uint32_t)ocr + 1UL);
  hz = F_CPU / den;
  hundredths = (uint8_t)(((F_CPU % den) * 100UL) / den);
}

static void printHz(uint16_t freq_hz) {
  uint16_t ocr = ocrForFrequency(freq_hz);
  uint32_t hz = 0;
  uint8_t frac = 0;
  actualFrequency(ocr, hz, frac);
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
  uint16_t ocr = ocrForFrequency(g_freq_hz);
  g_loaded_ocr = ocr;
  g_burst_freq_hz = g_freq_hz;

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
  if (!g_running) {
    return;
  }

  // Unsigned subtraction is valid across the micros() wrap (~71.6 min)
  // as long as the true gap is shorter than 2^32 µs. These gaps are <= 2 s
  // and the timestamps are refreshed every cycle.
  uint32_t now = micros();
  if (g_in_burst) {
    if ((uint32_t)(now - g_burst_start_us) >= g_pulse_us) {
      outputIdle();
    }
    return;
  }
  if ((uint32_t)(now - g_cycle_start_us) >= g_period_us) {
    burstBegin();
    g_cycle_start_us = g_burst_start_us;
  }
}

static void printHelp() {
  Serial.println(F("Commands:"));
  Serial.println(F("  HELP"));
  Serial.println(F("  STATUS"));
  Serial.println(F("  FREQ <Hz>     25000 to 40000, steps of 500"));
  Serial.println(F("  PERIOD <ms>   500 to 2000"));
  Serial.println(F("  PULSE <ms>    1 to 100, must be < PERIOD"));
  Serial.println(F("  START"));
  Serial.println(F("  STOP"));
  Serial.println(F("  TEST          bench-scope notes, does not start output"));
  Serial.println(F("D9 is a logic square wave for an external driver, not a transducer."));
}

static void printTestNotes() {
  Serial.println(F("TEST_MODE bench check, no transducer and no power amplifier:"));
  Serial.println(F("  Probe D9 for the carrier and D8 for the burst gate."));
  Serial.println(F("  Probe ground is Arduino GND."));
  Serial.println(F("  Fit pull-downs on D8 and D9 before a driver exists."));
  Serial.print(F("  Requested "));
  Serial.print(g_freq_hz);
  Serial.print(F(" Hz, timer produces "));
  printHz(g_freq_hz);
  Serial.println();
  Serial.println(F("  A 50% logic square wave has odd harmonics. Acoustic output is TBD."));
#if TEST_MODE
  Serial.println(F("  TEST_MODE compile flag is 1."));
#else
  Serial.println(F("  TEST_MODE compile flag is 0. Set it to 1 in the sketch for a boot warning."));
#endif
}

static void printStatus() {
  Serial.print(F("STATE "));
  Serial.println(g_running ? F("running") : F("stopped"));
  Serial.print(F("BURST "));
  Serial.println(g_in_burst ? F("on") : F("off"));
  Serial.print(F("FREQ requested "));
  Serial.print(g_freq_hz);
  Serial.print(F(" Hz, actual "));
  printHz(g_freq_hz);
  Serial.println();
  if (g_in_burst) {
    Serial.print(F("FREQ generating "));
    Serial.print(g_burst_freq_hz);
    Serial.print(F(" Hz, actual "));
    printHz(g_burst_freq_hz);
    Serial.println();
  }
  Serial.print(F("PERIOD "));
  Serial.print(g_period_ms);
  Serial.println(F(" ms"));
  Serial.print(F("PULSE "));
  Serial.print(g_pulse_ms);
  Serial.println(F(" ms"));
  Serial.println(F("PINS D9 carrier OC1A, D8 enable, idle level LOW"));
  Serial.println(F("NOTE 5 V GPIO cannot drive a transducer. External driver is TBD."));
}

static bool parseU16(const char *text, uint16_t &value) {
  if (text == nullptr || text[0] == '\0') {
    return false;
  }
  char *end = nullptr;
  unsigned long parsed = strtoul(text, &end, 10);
  while (end != nullptr && *end == ' ') {
    end++;
  }
  if (end == text || end == nullptr || *end != '\0' || parsed > 65535UL) {
    return false;
  }
  value = (uint16_t)parsed;
  return true;
}

static void applyTimingCache() {
  g_period_us = (uint32_t)g_period_ms * 1000UL;
  g_pulse_us = (uint32_t)g_pulse_ms * 1000UL;
}

static void handleLine(char *line) {
  while (*line == ' ') {
    line++;
  }
  if (*line == '\0') {
    return;
  }

  char *arg = line;
  while (*arg != '\0' && *arg != ' ') {
    if (*arg >= 'a' && *arg <= 'z') {
      *arg = (char)(*arg - ('a' - 'A'));
    }
    arg++;
  }
  if (*arg != '\0') {
    *arg = '\0';
    arg++;
    while (*arg == ' ') {
      arg++;
    }
  }

  if (strcmp(line, "HELP") == 0) {
    if (*arg != '\0') {
      Serial.println(F("ERR HELP takes no argument"));
      return;
    }
    printHelp();
    return;
  }
  if (strcmp(line, "STATUS") == 0) {
    if (*arg != '\0') {
      Serial.println(F("ERR STATUS takes no argument"));
      return;
    }
    printStatus();
    return;
  }
  if (strcmp(line, "TEST") == 0) {
    if (*arg != '\0') {
      Serial.println(F("ERR TEST takes no argument"));
      return;
    }
    printTestNotes();
    return;
  }
  if (strcmp(line, "START") == 0) {
    if (*arg != '\0') {
      Serial.println(F("ERR START takes no argument"));
      return;
    }
    if (g_running) {
      Serial.println(F("ERR already running; send STOP first"));
      return;
    }
    g_running = true;
    burstBegin();
    g_cycle_start_us = g_burst_start_us;
    Serial.print(F("OK START actual "));
    printHz(g_burst_freq_hz);
    Serial.println();
    return;
  }
  if (strcmp(line, "STOP") == 0) {
    if (*arg != '\0') {
      Serial.println(F("ERR STOP takes no argument"));
      return;
    }
    g_running = false;
    outputIdle();
    Serial.println(F("OK STOP pins LOW"));
    return;
  }
  if (strcmp(line, "FREQ") == 0) {
    uint16_t freq = 0;
    if (!parseU16(arg, freq)) {
      Serial.println(F("ERR FREQ <Hz>, example FREQ 30000"));
      return;
    }
    if (freq < FREQ_MIN_HZ || freq > FREQ_MAX_HZ || (freq % FREQ_STEP_HZ) != 0) {
      Serial.println(F("ERR frequency must be 25000 to 40000 Hz in 500 Hz steps"));
      return;
    }
    g_freq_hz = freq;
    Serial.print(F("OK FREQ actual "));
    printHz(g_freq_hz);
    if (g_in_burst && g_burst_freq_hz != g_freq_hz) {
      Serial.print(F("; applies on next burst"));
    }
    Serial.println();
    return;
  }
  if (strcmp(line, "PERIOD") == 0) {
    uint16_t period = 0;
    if (!parseU16(arg, period)) {
      Serial.println(F("ERR PERIOD <ms>, example PERIOD 1000"));
      return;
    }
    if (period < PERIOD_MIN_MS || period > PERIOD_MAX_MS) {
      Serial.println(F("ERR period must be 500 to 2000 ms"));
      return;
    }
    if (g_pulse_ms >= period) {
      Serial.println(F("ERR period must be greater than the current pulse width"));
      return;
    }
    g_period_ms = period;
    applyTimingCache();
    Serial.print(F("OK PERIOD "));
    Serial.print(g_period_ms);
    Serial.println(F(" ms"));
    return;
  }
  if (strcmp(line, "PULSE") == 0) {
    uint16_t pulse = 0;
    if (!parseU16(arg, pulse)) {
      Serial.println(F("ERR PULSE <ms>, example PULSE 10"));
      return;
    }
    if (pulse < PULSE_MIN_MS || pulse > PULSE_MAX_MS) {
      Serial.println(F("ERR pulse must be 1 to 100 ms"));
      return;
    }
    if (pulse >= g_period_ms) {
      Serial.println(F("ERR pulse must be shorter than the repetition period"));
      return;
    }
    g_pulse_ms = pulse;
    applyTimingCache();
    Serial.print(F("OK PULSE "));
    Serial.print(g_pulse_ms);
    Serial.println(F(" ms"));
    return;
  }

  Serial.println(F("ERR unknown command; send HELP"));
}

static void serviceSerial() {
  while (Serial.available() > 0) {
    int raw = Serial.read();
    if (raw < 0) {
      return;
    }
    char ch = (char)raw;
    if (ch == '\r' || ch == '\n') {
      if (g_line_overflow) {
        Serial.println(F("ERR line too long"));
      } else if (g_line_len > 0) {
        g_line[g_line_len] = '\0';
        handleLine(g_line);
      }
      g_line_len = 0;
      g_line_overflow = false;
      continue;
    }
    if (g_line_overflow) {
      continue;
    }
    if (g_line_len + 1 >= LINE_MAX) {
      g_line_overflow = true;
      g_line_len = 0;
      continue;
    }
    g_line[g_line_len++] = ch;
  }
}

void setup() {
  // Direction and idle level before Serial.begin, which can block on some hosts.
  pinMode(PIN_ENABLE, OUTPUT);
  pinMode(PIN_CARRIER, OUTPUT);
  TIMSK1 = 0;
  outputIdle();

  Serial.begin(SERIAL_BAUD);
#if TEST_MODE
  Serial.println(F("TEST_MODE: scope on D9/D8 only. Do not connect a transducer or amplifier."));
#endif
  Serial.println(F("RoboSub pinger idle. Pins LOW until START. Send HELP."));
  Serial.print(F("Defaults: "));
  Serial.print(g_freq_hz);
  Serial.print(F(" Hz requested, actual "));
  printHz(g_freq_hz);
  Serial.print(F(", period "));
  Serial.print(g_period_ms);
  Serial.print(F(" ms, pulse "));
  Serial.print(g_pulse_ms);
  Serial.println(F(" ms"));
}

void loop() {
  servicePinger();
  serviceSerial();
}
