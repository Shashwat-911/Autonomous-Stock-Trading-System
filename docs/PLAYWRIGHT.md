# Playwright browser tests

This branch contains runnable Playwright tests, a local browser target, pinned Node dependencies, HTML/JUnit reports, traces, screenshots, videos on failure, and a GitHub Actions workflow.

## What is actually tested

The existing cloud monitoring HTML and HTTP handler are tested against temporary synthetic session logs. The cloud launch loop is now guarded by `__main__`, allowing the monitor to be loaded without starting trading. No broker keys, broker requests, orders, calendar queries, or post-session publishing are used by these tests.

Coverage: Health and runner status; session history navigation; escaped log content; missing-log 404; debug empty state; mobile navigation.

## Install and run

Use Node.js 20+ and Python 3.12+ from your terminal. The three non-RAG suites use Python's standard library and existing dependency-free project modules. They do not require the full ML/trading dependency stack.

```sh
npm ci
npx playwright install chromium
npm run test:e2e
```

If Python is not named `python`, set `PLAYWRIGHT_PYTHON` to its executable. For example, in PowerShell:

```powershell
$env:PLAYWRIGHT_PYTHON = 'C:\path\to\python.exe'
npm run test:e2e
```

The test runner starts and stops its server automatically. Default port: **9101**; change with `PLAYWRIGHT_PORT` if needed. An occupied port fails explicitly rather than silently testing another app.

```sh
# Interactive test runner, headed debugging, reports and all browser engines
npm run test:e2e:ui
npm run test:e2e:headed
npm run test:e2e:report
npx playwright install chromium firefox webkit
npm run test:e2e:all
```

Failure artifacts are under `test-results/`; the HTML report is under `playwright-report/`. Both are ignored by Git. Open a failure trace with `npx playwright show-trace path/to/trace.zip`. The CI workflow installs all three engines and uploads evidence for 14 days.

## Browser workshop and ATF import

1. In ATF, paste the repository root URL: `https://github.com/Shashwat-911/Autonomous-Stock-Trading-System`.
2. Enter **playwright** in the **Branch, tag or commit** field. Leaving it empty imports the default `main` branch, which does not contain this setup.
3. Analyze the repository. The Playwright tab discovers `playwright.config.js`, `tests/e2e/*.spec.js`, and package scripts.
4. In a terminal in this repository, run `npm run playwright:serve` to keep the browser target available. Stop this server before `npm run test:e2e`, since tests manage their own server.
5. Run the commands below in ATF's command editor, or open the URL in your own browser. ATF's command runner does not execute the imported native suite; `npm run test:e2e` does.

```text
goto "http://127.0.0.1:9101/logs"
expect-title "Trading Logs — Autonomous Stock Trader"
expect-text ".log-content" "PLAYWRIGHT SYNTHETIC SESSION"
click "text=Debug Log"
expect-text ".log-content" "No debug log found."
screenshot
```

To record more native Playwright tests, leave `npm run playwright:serve` running and use `npm run playwright:record` in a second terminal. Save the generated code under `tests/e2e/` and add assertions relevant to the project.

## Files

- `package.json` / `package-lock.json`: reproducible Playwright dependency and commands.
- `playwright.config.js`: Chromium/Firefox/WebKit projects, local server lifecycle and evidence.
- `scripts/playwright-server.cjs`: shell-free Python launcher supporting Windows paths.
- `scripts/playwright_server.py`: repository-specific browser target.
- `tests/e2e/`: executable browser and request tests.
- `.github/workflows/playwright.yml`: push/PR/manual browser checks.

A passing suite confirms only these listed workflows. The synthetic fixtures and frontend-only tests do not establish correctness of the full trading, surveillance, medical-image or RAG system.
