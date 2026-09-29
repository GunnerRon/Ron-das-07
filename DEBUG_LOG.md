# Debug Log: `process_data.py`

A record of how the legacy `process_data.py` script was understood, diagnosed,
tested, and fixed with an AI pair-programmer. Each step lists the prompt used,
the most useful parts of the AI's response, and notes on the reasoning.

> The **Notes** sections are a first draft of my reasoning. Edit them to match
> your own thinking.

| Step | Outcome | Commit |
|------|---------|--------|
| 1. Understand the codebase | Mental model and list of concerns | none (analysis only) |
| 2. Diagnose the bug | Root cause: failures swallowed, success falsely reported | none (analysis only) |
| 3. Reproduce with a test | `TEST_CASES.py`: 3 of 6 tests fail on the original code | `831088d` |
| 4. Fix and refactor | All 6 tests pass; outputs unchanged | `aa91e5b` |

---

## Step 1: Understand the codebase

### Prompt

> This is a legacy Python script. Please provide a high-level summary of what
> it's supposed to do. Then, break down your explanation function by function,
> detailing the purpose of each, its expected inputs and outputs, and any side
> effects. Finally, identify any potential areas of concern or parts of the
> code that seem overly complex or inefficient.

### Key parts of the AI response

**Summary:** a batch job for customer analytics. It loads `customers.csv` into
a dict keyed by `customer_id`. It then reads `transactions.csv` and adds each
amount to that customer's `total_spent` and `transaction_count`. It writes
three JSON reports (customer summary, metrics, transactions) and exports the
customer data as CSV and JSON. All state lives on one `DataProcessor` object;
`main()` runs the steps with hard-coded file names.

**Function by function:**

| Function | Purpose | Output | Side effects |
|----------|---------|--------|--------------|
| `__init__` | Sets up empty `customers`, `transactions`, `reports` (`reports` is never used) | none | none |
| `load_data` | Reads the customer CSV | `bool` | Fills `self.customers`, logs |
| `process_transactions` | Reads transactions and updates customer totals | `bool` | Changes `transactions` and `customers` |
| `calculate_customer_metrics` | Totals, average, top 10 customers, category counts | `dict` | none |
| `find_matches` | Case-insensitive substring search on one field | `list` | none (never called) |
| `generate_report` | Writes one of three JSON reports | `bool` | Writes a file |
| `export_customer_data` | Exports customers as CSV or JSON | `bool` | Writes a file |
| `main` | Runs the whole pipeline | none | Writes 5 files |

**Most important concerns flagged:**
- `main()` ignores the return values of `generate_report` and
  `export_customer_data`, so it always logs "completed successfully".
- The broad `except Exception` handlers log only `str(e)` and drop the
  traceback.
- A bad row stops a file partway through and leaves the data half-updated.
  Running `process_transactions` twice double-counts.
- The average transaction value is skewed when transactions refer to unknown
  customers.
- Money is stored as `float`, and there is a trailing space in one `join_date`
  (confirmed in the output: `"2023-05-12 "`).
- Minor issues: `format` shadows a built-in name, an unused import, a
  hand-written sort and tally, and no tests.

### Notes

- I asked for a function-by-function breakdown before touching anything, so
  the assistant had to read all of the code, not just the part I suspected.
- The AI ran the script against the sample CSVs instead of only reading it.
  That turned up the `join_date` whitespace problem, which is easy to miss by
  reading alone.
- The first finding ("main ignores return values") turned out to be the core
  of the bug in Step 2.

---

## Step 2: Diagnose the specific bug

### Prompt

> Given the following function from the script and the associated error log,
> what is the most likely root cause of the failure? Please explain your
> reasoning step-by-step, referencing specific lines of code and the error
> message.

Context supplied: `export_customer_data` (lines 173-200), the calls in
`main()` (lines 224-227), and the full `error.log`:

```
2024-01-15 02:30:16,123 - INFO - Exported customer data to customers_export.csv
2024-01-15 02:30:16,234 - ERROR - Error exporting data: 'dict' object has no attribute 'keys'
2024-01-15 02:30:16,235 - ERROR - Data processing completed successfully
```

### Key parts of the AI response

1. **Which call failed:** the CSV export logged success, and the JSON export
   success line is missing. So the failing call is the JSON export
   (`main()` line 225).
2. **No traceback:** the message comes from the catch-all at line 199, which
   logs only `{e}`. The failing line cannot be identified from the log.
3. **The message cannot come from this code.** The AI tested this: a real
   `dict` always has `.keys()`. `json.dump` fails with `TypeError: Object of
   type X is not JSON serializable`, not an `AttributeError`. A non-dict record
   in the CSV path gives `'str' object…` or `'NoneType' object…`, never
   `'dict'`.
4. **The log came from a different version:** it has timestamps (this script's
   `basicConfig` does not add them), logs the final line at `ERROR` (the code
   uses `logger.info`), and shows 150 customers and 1250 transactions, where
   the samples have 5 and 10. The most likely source is a Python 2-era idiom
   such as `.iterkeys()` or `.has_key()`, which gives exactly this kind of
   message on Python 3.
5. **The certain bug, still in the current code:** `export_customer_data`
   returns `False` (line 200), `main()` ignores it (line 225), and logs success
   (line 227). This is why the log contradicts itself.

**Recommended fixes:** use `logger.exception` in the handlers, and make
`main()` check return values and exit non-zero.

### Notes

- The error message looked like the obvious clue. The more useful signal was
  the contradiction between the last two log lines: an error followed by
  "completed successfully".
- I didn't accept a guessed explanation for the `AttributeError`. The AI showed
  by experiment that this code can't produce it. That separated what we could
  prove (failures are swallowed) from what we could only suspect (the exact
  exception in the production version).
- Lesson: when the log doesn't match the code, check the log's format and data
  volume. They showed it came from a different version.

---

## Step 3: Write a test to reproduce the bug

### Prompt

> Based on your analysis of the bug, write a Python unit test using the
> 'unittest' library that is specifically designed to fail in the same way the
> error log shows. This test should call the problematic function with data
> that triggers the bug.

### Key parts of the AI response

- No data can make the current code raise the logged error, so the test
  replaces `json.dump` with a stand-in that raises the exact exception from
  the log, only for `customers_export.json`. Every other file is written
  normally.
- Each test runs in a temporary folder with copies of the sample CSVs, because
  `main()` uses hard-coded relative paths.

```python
def _json_dump_failing_on_customer_export(obj, fp, *args, **kwargs):
    if os.path.basename(getattr(fp, "name", "")) == "customers_export.json":
        raise AttributeError("'dict' object has no attribute 'keys'")
    return _real_json_dump(obj, fp, *args, **kwargs)
```

Results against the original code (`python3 -m unittest TEST_CASES -v`):

| Test | Result | Shows |
|------|--------|-------|
| `test_error_from_log_is_raised_and_reported` | pass | Reproduces the exact error line from `error.log` |
| `test_main_does_not_claim_success_after_export_failure` | **FAIL** | `main()` logs "completed successfully" after the failure |
| `test_main_exits_non_zero_after_export_failure` | **FAIL** | The script exits with code 0 |
| `test_json_export_failure_logs_traceback` | **FAIL** | The error is logged without a traceback |
| `test_json_export_failure_returns_false` | pass | The export does report failure; `main()` ignores it |
| `test_json_export_round_trips` | pass | Control test: normal export works |

```
Ran 6 tests in 0.011s
FAILED (failures=3)
```

### Notes

- The three failing tests each match one symptom in `error.log`: the false
  success line, the exit code, and the missing traceback.
- I kept passing tests alongside them. One confirms we reproduced the exact log
  line. The other is a control, so the fix can't break normal behaviour
  without a test noticing.
- Injecting the exception is a deliberate trade-off: it reproduces the
  failure *path* faithfully without guessing at the production data.

---

## Step 4: Refactor and fix the code

### Prompt

> Refactor this function to fix the bug we identified. While doing so, also
> improve its performance. The current implementation uses inefficient nested
> for-loops; please replace this logic with a more performant method, such as
> using a dictionary lookup.

### Key parts of the AI response

The AI pointed out that the prompt's premise was wrong: **there are no nested
for-loops in `process_data.py`.** Every function goes through its data once,
and `process_transactions` already uses a dictionary lookup. It made the fix
plus the speed-ups the code actually allows.

**Fix:**

```python
failed = [output for output, ok in results.items() if not ok]
if failed:
    logger.error(f"Data processing failed; could not write: {', '.join(failed)}")
    sys.exit(1)

logger.info("Data processing completed successfully")
```

- `main()` checks every report and export result and exits 1 on failure. It
  also exits 1, instead of returning with code 0, when loading customers or
  transactions fails.
- All four catch-all handlers use `logger.exception(...)`, so tracebacks are
  logged.

**Performance:**
- `process_transactions` converts each amount once instead of twice, and does
  one `dict.get` lookup per row instead of three.
- `calculate_customer_metrics` uses `heapq.nlargest(10, ...)` instead of
  sorting every customer, and `Counter` instead of a hand-written tally.

**Test adjustment:** `test_error_from_log_is_raised_and_reported` compared the
whole log line exactly. Now that a traceback is appended to the line, it
checks that the line *starts with* the expected error message.

**Verification:**

```
New code:       Ran 6 tests ... OK
Original code:  FAILED (failures=3)      # same 3 tests, so they really catch the bug
```

- All five output files are the same as the original script's on the sample
  data, apart from `generated_at`.
- A missing `transactions.csv` exits 1. A healthy run exits 0.

### Notes

- The AI pushed back on the "nested for-loops" instruction instead of
  inventing a problem to match it. A refactor that answers a problem the code
  doesn't have only adds risk.
- Comparing outputs before and after mattered as much as the tests: the
  speed-ups had to leave every result unchanged.
- Running the new tests against the old code (via `git stash`) proved they
  catch the bug and would have failed without the fix.

---

## Open items / follow-ups

- Find the exact `AttributeError` by running the fixed script (which now logs
  tracebacks) against the 150-customer production data.
- Load and process data so that a bad row can't leave half-updated state, and
  make `process_transactions` safe to run twice.
- Trim whitespace in CSV fields, parse and validate dates, and use `Decimal`
  for money.
- Include `customer_id` in the `customer_summary` report, and exclude
  unknown-customer transactions consistently from the average.
