export type RealBusinessArtifact = 'web' | 'java-swing' | 'spring-mysql'

export interface RealBusinessScenario {
  id: `T${string}`
  title: string
  outputDir: string
  artifactKind: RealBusinessArtifact
  prompt: string
  expectedTools: string[]
  visualCheckpoints: string[]
  interactionProbe: string
  maxInputTokens: number
  maxOutputTokens: number
  timeoutMs: number
}

const BUDGET = {
  maxInputTokens: 200_000,
  maxOutputTokens: 48_000,
  timeoutMs: 45 * 60 * 1000
} as const

const commonRules = `
Windows guidance: use PowerShell or cmd-compatible commands. Do not use Unix-only timeout, find, grep, chmod, or shell syntax. Pass time limits through the tool timeout field, inspect stderr after a failed command, and repair the root cause instead of repeating the same failed command. Do not run validation against half-written files.
This is a real GUI Agent acceptance test, not a code-snippet generation task. Save every source file as UTF-8, record sources, dates, limits, missing data, commands, and unavailable capabilities honestly. Inspect the workspace, current time, and environment first. Report important progress, tool calls, recovery, and the final conclusion through visible GUI events. Complete PLAN, implementation, and static checks before opening a browser or desktop window. All artifacts must stay inside the requested Txx directory; never write to another Txx directory, the user home directory, or repository configuration. Deliver README.md, exact verification commands, actual interaction results, unresolved risks, and token/performance information. Never claim an action that was not actually performed.`

export const realBusinessScenarios: RealBusinessScenario[] = [
  {
    id: 'T01',
    title: 'Original offline runner game',
    outputDir: 'T01-runner',
    artifactKind: 'web',
    expectedTools: ['list_dir', 'write_file', 'run_command', 'open_file'],
    visualCheckpoints: ['start/pause/resume/restart controls', 'player, obstacles, score, speed', 'collision, game over, high score'],
    interactionProbe: 'Open the page in a real browser, start the game, use keyboard or touch movement at least three times, observe score, trigger a collision, restart, and verify the high score survives refresh.',
    ...BUDGET,
    prompt: `Create T01-runner in the current workspace. Build an original offline parkour/runner game that can really be played. Use only native HTML, CSS, and JavaScript; no React, CDN, remote images, remote fonts, or external runtime. Support keyboard and touch controls, start, pause, resume, restart, score, localStorage high score, increasing speed, obstacle collision, sound toggle, help text, and responsive layout. Keep every asset inside T01-runner. Write PLAN.md first, then index.html, styles.css, game.js, README.md, and TEST-REPORT.md; run a static check. Then start a local static site and really test movement/jump, score, collision/game-over, restart, refresh/high-score persistence, and narrow layout. Do not invent browser actions; mark anything impossible as unavailable with a reason. ${commonRules}`
  },
  {
    id: 'T02',
    title: 'Original platform jumper',
    outputDir: 'T02-platformer',
    artifactKind: 'web',
    expectedTools: ['list_dir', 'write_file', 'run_command', 'open_file'],
    visualCheckpoints: ['platform/player collision', 'enemies, coins, lives, checkpoint', 'win, respawn, pause, restart, level transition'],
    interactionProbe: 'Start level one in a real browser, move and jump, collect a coin, hit an enemy or fall, verify checkpoint respawn, pause/resume/restart, and enter level two.',
    ...BUDGET,
    prompt: `Create T02-platformer in the current workspace. Build an original horizontal platform-jumping game. The genre may evoke classic platform games, but do not use Nintendo names, characters, art, audio, or copied game code. Use native HTML, CSS, JavaScript, and local original SVG/Canvas graphics. Provide at least two different levels. Implement left/right movement, jump, gravity, platform collision, enemies, coins, lives, checkpoint, goal, level transition, start, pause, resume, restart, mute, help, level/score/life display, continuous-key handling, jump cooldown, landing, enemy collision, checkpoint respawn, and narrow touch controls. Write PLAN.md, run static checks and a minimal test, then launch the real game and complete at least level one. Verify failure, respawn, pause, restart, and level-two entry. ${commonRules}`
  },
  {
    id: 'T03',
    title: 'Company website with demo login and admin console',
    outputDir: 'T03-company',
    artifactKind: 'web',
    expectedTools: ['websearch', 'webfetch', 'skill', 'list_dir', 'write_file', 'run_command'],
    visualCheckpoints: ['responsive public home page', 'login failure and success', 'admin navigation, tables, charts, CRUD'],
    interactionProbe: 'Open the site, test wrong credentials and the clearly marked demo account, edit one record, refresh for persistence, switch modules, inspect a chart, and log out.',
    ...BUDGET,
    prompt: `Create T03-company in the current workspace. First call websearch at least three times and webfetch at least twice to research company website competitors, information architecture, and visual design. Create PLAN.md with source URLs, access times, adopted ideas, rejected ideas, and reasons. Then automatically search for and genuinely load one suitable frontend development Skill. Install it only into the isolated test Skill directory, and record its name, version, source, and load event without touching the user Skill directory. Build an original responsive company website with home, products/services, team, cases, contact form, and a clearly labeled demo authentication flow. A successful demo login must open an admin console with users, orders, content, settings, and analytics modules; support validation, search/filter, CRUD, persistence after refresh, and logout. Never present demo credentials as real security. Deliver build commands, sources.md, README.md, TEST-REPORT.md, and screenshot notes. Really perform failed login, demo login, data edit, refresh, module switching, chart inspection, and logout. ${commonRules}`
  },
  {
    id: 'T04',
    title: 'Five-day four-night Guangzhou to Suzhou and Hangzhou plan',
    outputDir: 'T04-travel',
    artifactKind: 'web',
    expectedTools: ['datetime', 'websearch', 'webfetch', 'write_file', 'run_command'],
    visualCheckpoints: ['daily schedule', 'itemized budget and total', 'sources, rain plan, alternatives'],
    interactionProbe: 'Open the guide, switch dates, cities, transport, and styling options, inspect the budget view, and verify the total remains at or below CNY 3000.',
    ...BUDGET,
    prompt: `Create T04-travel in the current workspace. First call datetime and record the current date. Plan a five-day four-night Suzhou plus Hangzhou trip from and back to Guangzhou with a hard total budget of no more than CNY 3000 and one makeup/styling session. Use websearch and webfetch for transport, lodging, tickets, food, local transport, styling, and contingency costs; record source URL, access date, price, range, and uncertainty. Do not invent live inventory, booking status, or unverifiable exact prices. Deliver PLAN.md, an interactive webpage, budget CSV, sources.md, README.md, and TEST-REPORT.md. The page must include a daily timetable, city switch, cost categories, total-budget validation, rain plan, alternatives, and price-change warnings. Actually operate date/cost filters and the budget view and verify the total is within CNY 3000. If only a range is available, show the range and mark uncertainty. ${commonRules}`
  },
  {
    id: 'T05',
    title: 'Java Swing number bomb game',
    outputDir: 'T05-number-bomb',
    artifactKind: 'java-swing',
    expectedTools: ['datetime', 'list_dir', 'write_file', 'run_command', 'open_file'],
    visualCheckpoints: ['Swing window and controls', 'invalid input and range feedback', 'win/loss/restart states'],
    interactionProbe: 'Compile with javac -encoding UTF-8, launch the real Swing window, test invalid input, narrowing range, bomb or safe target, restart, and close.',
    ...BUDGET,
    prompt: `Create T05-number-bomb in the current workspace. First call datetime and write the current time into the test report. Use Java 17 and Swing to build a real launchable number bomb game; HTML or a screenshot is not an acceptable substitute. Generate a random bomb and range, narrow lower and upper bounds after every guess, lose on the bomb, and win on a safe target. Provide at least normal and hard difficulty, maximum attempts, timer, guess history, current range, new-game button, Enter submit, empty/decimal/letter/out-of-range validation, close handling, and clean repeated restart state. Save UTF-8 sources, README.md, DEVELOPMENT.md, TEST-REPORT.md, compile script, and test instructions. On Windows explicitly run javac -encoding UTF-8, compile and run a minimal test, then launch a real Swing window and complete invalid input, range narrowing, win or loss, and restart. Record JDK, commands, screenshots, and close/cleanup evidence. ${commonRules}`
  },
  {
    id: 'T06',
    title: 'One-year market-data BI and risk analysis',
    outputDir: 'T06-market-bi',
    artifactKind: 'web',
    expectedTools: ['datetime', 'websearch', 'webfetch', 'write_file', 'run_command'],
    visualCheckpoints: ['normalized price curves', 'date/asset/metric controls and tooltips', 'detail table, gaps, and risk disclosure'],
    interactionProbe: 'Open the BI page, switch date range, assets, metrics, and benchmark, inspect tooltips and detail table, and verify missing data and sources are traceable.',
    ...BUDGET,
    prompt: `Create T06-market-bi in the current workspace. Call datetime first. Collect verifiable data for the last year for gold, silver, an A-share technology index or STAR 50 plus a disclosed representative technology-stock basket, Nasdaq Composite, and S&P 500. Record source URL, extraction time, frequency, currency, missing values, and methodology for every dataset. Align trading dates and calculate cumulative return, annualized volatility, maximum drawdown, and correlation. Produce raw CSV, cleaned/calculated data, an interactive BI webpage, README.md, sources.md, and TEST-REPORT.md. The page must provide date filter, asset filter, normalized benchmark, metric switcher, tooltips, detail table, data-gap warnings, and a risk disclaimer. Opinions must be evidence-bounded scenario analysis, not personalized financial advice; mark inaccessible data unavailable rather than fabricating it. Open the page and really operate filters, charts, tooltips, and the detail table. ${commonRules}`
  },
  {
    id: 'T07',
    title: 'Guangzhou family electric-vehicle decision system',
    outputDir: 'T07-ev',
    artifactKind: 'web',
    expectedTools: ['datetime', 'websearch', 'webfetch', 'write_file', 'run_command'],
    visualCheckpoints: ['vehicle comparison table', 'five-year TCO chart', 'linked recommendation by weights and mileage'],
    interactionProbe: 'Adjust budget, annual mileage, and price/range/safety weights, compare at least three vehicles, and verify TCO and recommendation changes explainably.',
    ...BUDGET,
    prompt: `Create T07-ev for a three-person Guangzhou family. The scenario is CNY 150,000-250,000 purchase budget, 40 km daily commute, 15,000 km per year, and five-year ownership. Call datetime first. Research at least six vehicles for price, range, charging/refueling, insurance, maintenance, depreciation, and safety; record source, date, ranges, and uncertainty, and never fabricate live promotions. Calculate five-year total cost of ownership. Let the user adjust budget, annual mileage, charging assumptions, and price/range/safety/space weights; filters, tables, charts, and recommendation must update together. Deliver webpage, data CSV, sources.md, README.md, and test report. Actually change budget, mileage, and weights and verify an explainable recommendation-order change with data validity and risk displayed. ${commonRules}`
  },
  {
    id: 'T08',
    title: 'Guangzhou rental and moving decision system',
    outputDir: 'T08-rental',
    artifactKind: 'web',
    expectedTools: ['datetime', 'websearch', 'webfetch', 'write_file', 'run_command'],
    visualCheckpoints: ['area filter and schematic map', 'total budget and commute comparison', 'moving calendar and contract checklist'],
    interactionProbe: 'With Zhujiang New Town commute constraints, filter and compare at least three areas, adjust rent/commute/amenity weights, and inspect budget, map, calendar, and risk checklist.',
    ...BUDGET,
    prompt: `Create T08-rental for a person commuting to Zhujiang New Town, with monthly rent at most CNY 3500 and one-way commute at most 60 minutes. Research 6-10 candidate areas or reliable price ranges. If actual listings are unavailable, do not fabricate exact addresses, listings, inventory, or transport times. Calculate deposit, agent fee, property fee, utilities, commute, and moving costs; analyze contract, noise, repairs, termination, and commute uncertainty. Deliver an interactive webpage with filters, ranking, scoring, schematic map, budget, moving calendar, move-in checklist, sources, CSV, README.md, sources.md, and TEST-REPORT.md. Actually filter and compare at least three options, change weights, verify ranking and total-budget changes, and label all interval estimates. ${commonRules}`
  },
  {
    id: 'T09',
    title: 'Java Spring MySQL coffee-shop full-stack system',
    outputDir: 'T09-coffee',
    artifactKind: 'spring-mysql',
    expectedTools: ['list_dir', 'write_file', 'run_command', 'open_file'],
    visualCheckpoints: ['login, product, inventory screens', 'inventory after an order', 'date-filtered revenue console'],
    interactionProbe: 'Use only a temporary MySQL schema and least-privilege user; really log in/out, perform product and inventory CRUD, place an order, and verify stock and revenue updates.',
    ...BUDGET,
    prompt: `Create T09-coffee in the current workspace as a real runnable coffee-shop full-stack system. Use Java 17, project-local Maven 3.9.16, Spring Boot 4.1.0, and MySQL 8. Database URL, username, password, and demo admin password must come from environment variables and must never be written to source, README, prompt, logs, or Git. Use Flyway for users, products, inventory, orders, and order_items with migration and rollback documentation. Implement REST backend and static frontend with login, session authentication, logout, product CRUD, inventory CRUD, transactional order stock decrement, low-stock alerts, and date-filtered revenue admin console. Run Maven unit/integration tests and API smoke tests. Really perform login, logout, product edit, order, stock change, and revenue update. Use only a temporary schema and least-privilege user; if MySQL 8, the specified Maven, or SHA-512 verification is unavailable, record unavailable instead of silently substituting an in-memory database. Deliver README.md, DEVELOPMENT.md, API.md, ARCHITECTURE.md, SECURITY.md, MIGRATION-ROLLBACK.md, and TEST-REPORT.md, plus schema/user cleanup proof. ${commonRules}`
  }
]

export interface BatchPrompt {
  id: string
  prompt: string
  outputDir: string
}

export function buildBatchPrompts(): { independent: BatchPrompt[]; sequential: BatchPrompt[] } {
  const prompts = realBusinessScenarios.map(({ id, prompt, outputDir }) => ({ id, prompt, outputDir }))
  return { independent: prompts, sequential: prompts }
}
