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
This is a real GUI Agent acceptance test, not a code-snippet generation task. Save every source file as UTF-8, record sources, dates, limits, missing data, commands, and unavailable capabilities honestly. Inspect the workspace, current time, and environment first. Report important progress, tool calls, recovery, and the final conclusion through visible GUI events. Complete PLAN, implementation, and static checks before opening a browser or desktop window. All artifacts must stay inside the requested Txx directory; never write to another Txx directory, the user home directory, or repository configuration. Deliver README.md and TEST-REPORT.md by actually calling the write tool for each file before the Final Answer; listing a filename in a table does not create it. If those documents are still missing, write them immediately and do not re-read game or page source. Before the Final Answer, list the Txx directory and confirm every required file exists on disk. Never claim an action that was not actually performed.`

const nativePageRules = 'Use only native HTML, CSS, and JavaScript; no CDN, remote Chart.js, remote images, or remote fonts. Close every non-void HTML tag (especially label, div, section, and script); unclosed tags fail write-tool format validation.'

const gamePlayRules = `
Playable-game contract: the Start/Play control must hide the menu overlay so #btn-start / #startBtn is not visible, and the game must then actually simulate. Keep a live DOM #score (or #scoreVal) that can increase and a DOM #stateLabel or #state whose text becomes running/playing/运行中 after Start. Do not treat a painted canvas behind a still-visible menu as playing. Do not call hideOverlay/loadLevel during init in a way that is immediately undone by showing the menu, and never let AudioContext or sound setup abort the Start click before the overlay is hidden.`

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
    prompt: `Create T01-runner in the current workspace. Build an original offline parkour/runner game that can really be played. Use only native HTML, CSS, and JavaScript; no React, CDN, remote images, remote fonts, or external runtime. Support keyboard and touch controls, start, pause, resume, restart, score, localStorage high score, increasing speed, obstacle collision, sound toggle, help text, and responsive layout. Keep every asset inside T01-runner. Write PLAN.md first, then index.html, styles.css, game.js, README.md, and TEST-REPORT.md; run a static check. Then start a local static site and really test movement/jump, score, collision/game-over, restart, refresh/high-score persistence, and narrow layout. Do not invent browser actions; mark anything impossible as unavailable with a reason. ${gamePlayRules} ${commonRules}`
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
    prompt: `Create T02-platformer in the current workspace. Build an original horizontal platform-jumping game. The genre may evoke classic platform games, but do not use Nintendo names, characters, art, audio, or copied game code. Use native HTML, CSS, JavaScript, and local original SVG/Canvas graphics. Provide at least two different levels. Implement left/right movement, jump, gravity, platform collision, enemies, coins, lives, checkpoint, goal, level transition, start, pause, resume, restart, mute, help, level/score/life display, continuous-key handling, jump cooldown, landing, enemy collision, checkpoint respawn, and narrow touch controls. Write PLAN.md, README.md, TEST-REPORT.md, index.html, and the game sources with the write tool before launching the game. Run static checks and a minimal test, then launch the real game and complete at least level one. Verify failure, respawn, pause, restart, and level-two entry. ${gamePlayRules} ${commonRules}`
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
    prompt: `Create T03-company in the current workspace. First call websearch at least three times and webfetch at least twice to research company website competitors, information architecture, and visual design. Create PLAN.md with source URLs, access times, adopted ideas, rejected ideas, and reasons. Then call the skill tool to load one suitable frontend development Skill already present under the isolated RXYCODE_SKILLS_DIRS directory (ui-ux-pro-max is available). Do not call download_skill. Record the Skill name, version, source, and load event without touching the user Skill directory. Build an original responsive static HTML/CSS/JavaScript company website; Java, Spring, Maven, or a backend substitute is a hard failure for this task. Include home, products/services, team, cases, contact form, and a clearly labeled demo authentication flow. A successful demo login must open a real admin.html console (not admin.js alone) with visible 用户管理, 订单管理, 内容管理, 设置, and 分析 navigation; support validation, search/filter, CRUD, persistence after refresh, and logout. Never present demo credentials as real security. Deliver build commands, sources.md, README.md, TEST-REPORT.md, and screenshot notes by actually calling the write tool for each file. Really perform failed login, demo login, data edit, refresh, module switching, chart inspection, and logout. ${commonRules}`
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
    prompt: `Create T06-market-bi in the current workspace. Call datetime first. Then call websearch at least three times and webfetch at least twice for gold, silver, an A-share technology index or STAR 50 plus a disclosed representative technology-stock basket, Nasdaq Composite, and S&P 500. Do not probe pandas, numpy, matplotlib, Yahoo Finance, python, node, pip, or general internet connectivity with bash; those probes hang and starve the deliverable. Do not write _probe.py. Do not call workflow. After the required searches, immediately call the write tool for index.html, CSV files, sources.md, README.md, and TEST-REPORT.md. If a source is unreachable, mark it UNAVAILABLE in sources.md and still write the interactive BI page plus CSV files that the page can load. Record source URL, extraction time, frequency, currency, missing values, and methodology for every dataset. Align trading dates and calculate cumulative return, annualized volatility, maximum drawdown, and correlation. Produce raw CSV, cleaned/calculated data, an interactive BI webpage, README.md, sources.md, and TEST-REPORT.md. Use only native HTML, CSS, and JavaScript; no CDN, remote Chart.js, remote images, or remote fonts. The page must provide date filter, asset filter, normalized benchmark, metric switcher, tooltips, detail table, data-gap warnings, and a risk disclaimer. Opinions must be evidence-bounded scenario analysis, not personalized financial advice; mark inaccessible data unavailable rather than fabricating it. Open the page and really operate filters, charts, tooltips, and the detail table. ${commonRules}`
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
    prompt: `Create T07-ev for a three-person Guangzhou family. The scenario is CNY 150,000-250,000 purchase budget, 40 km daily commute, 15,000 km per year, and five-year ownership. Call datetime first. Then call websearch at least three times and webfetch at least twice. Do not probe pandas, numpy, matplotlib, Yahoo Finance, python, node, pip, or general internet connectivity with bash; those probes hang and starve the deliverable. Do not write _probe.py. Do not call workflow. After the required searches, immediately call the write tool for index.html, CSV, sources.md, README.md, and TEST-REPORT.md. If a source is unreachable, mark it UNAVAILABLE in sources.md and still write the interactive page plus CSV. Research at least six vehicles for price, range, charging/refueling, insurance, maintenance, depreciation, and safety; record source, date, ranges, and uncertainty, and never fabricate live promotions. Calculate five-year total cost of ownership. Let the user adjust budget, annual mileage, charging assumptions, and price/range/safety/space weights; filters, tables, charts, and recommendation must update together. Deliver webpage, data CSV, sources.md, README.md, and TEST-REPORT.md. Actually change budget, mileage, and weights and verify an explainable recommendation-order change with data validity and risk displayed. ${nativePageRules} ${commonRules}`
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
    prompt: `Create T08-rental for a person commuting to Zhujiang New Town, with monthly rent at most CNY 3500 and one-way commute at most 60 minutes. Call datetime first. Then call websearch at least three times and webfetch at least twice. Do not probe pandas, numpy, matplotlib, Yahoo Finance, python, node, pip, or general internet connectivity with bash; those probes hang and starve the deliverable. Do not write _probe.py. Do not call workflow. Java, Spring, Maven, pom.xml, or a backend substitute is a hard failure; this is a static HTML/CSS/JS decision page. After the required searches, immediately call the write tool for index.html, CSV, sources.md, README.md, and TEST-REPORT.md. If a source is unreachable, mark it UNAVAILABLE in sources.md and still write the interactive page plus CSV. Research 6-10 candidate areas or reliable price ranges. If actual listings are unavailable, do not fabricate exact addresses, listings, inventory, or transport times. Calculate deposit, agent fee, property fee, utilities, commute, and moving costs. The page must include a visible 合同与风险 section in index.html covering 合同条款, 解约/退租, 噪音, and 维修; do not hide that checklist only in JavaScript. Deliver an interactive webpage with filters, ranking, scoring, schematic map, budget, moving calendar, move-in checklist, sources, CSV, README.md, sources.md, and TEST-REPORT.md. Actually filter and compare at least three options, change weights, verify ranking and total-budget changes, and label all interval estimates. ${nativePageRules} ${commonRules}`
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
    prompt: `Create T09-coffee in the current workspace as a real runnable coffee-shop full-stack system. Use Java 17, project-local Maven 3.9.16, Spring Boot 4.1.0, and MySQL 8. A Python, Flask, Django, or SQLite substitute is a hard failure. The first pom.xml write must declare spring-boot-starter-flyway and flyway-mysql; flyway-core without the starter is a hard failure. Call the write tool first for pom.xml, REST *Controller.java, src/main/resources/static/index.html, Flyway SQL, and application.yml; write() creates parent directories, so do not mkdir and do not download Maven until those files exist. The directory name is exactly T09-coffee with a hyphen; writing T09_coffee is a hard failure. Do not write _probe.py or _probe*.bat. Do not probe MySQL, TCP, or env with bash before pom.xml and *Controller.java exist in T09-coffee. Do not stop after an Application class plus one model: that skeleton is a hard failure. Any package under src/main/java is valid; do not rename or relocate *Controller.java once they exist. Java must compile: use java.math.BigDecimal for money and int for stock; do not assign double to Integer or BigDecimal. For Spring Boot 4.1 tests, add spring-boot-starter-webmvc-test and import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc; do not use the Boot 3 package org.springframework.boot.test.autoconfigure.web.servlet or org.springframework.boot.test.autoconfigure.webmvc. Do not import com.fasterxml.jackson.databind; Boot 4 JsonNode/ObjectMapper are tools.jackson.databind, or use jsonPath and skip Jackson types. src/test/java *Test.java must use @SpringBootTest and MockMvc and must live in the same package as @SpringBootApplication or declare @SpringBootTest(classes=...); a class-load check of Application.getSimpleName() is a hard failure. Do not add a second test class in com.rxycode.t09coffee if the app is in another package, and do not assert $.token for session form login. When inserting Inventory, set updatedAt; DATETIME NOT NULL cannot be null. Do not @ExceptionHandler(Exception.class) to HTTP 500. MYSQL_ADMIN_PASSWORD is the database password, not the demo login password. Do not set spring.jackson.serialization.write-dates-as-timestamps; Boot 4 Jackson 3 fails context load with No enum constant write-dates-as-timestamps. Delete that block or use WRITE_DATES_AS_TIMESTAMPS. Spring Security 7 has no DaoAuthenticationProvider() no-arg constructor and no setUserDetailsService: use new DaoAuthenticationProvider(userDetailsService) then setPasswordEncoder, or omit that bean. Store user roles as ADMIN without a ROLE_ prefix when calling User.roles(); roles() adds ROLE_ itself. Calling roles("ROLE_ADMIN") or wrapping ROLE_ADMIN in SimpleGrantedAuthority then roles() causes a 500: ROLE_ADMIN cannot start with ROLE_. Flyway must create users, products, inventory, orders, and order_items before any DataSeeder SQL; use ApplicationRunner or @DependsOn("flyway"), not @PostConstruct queries against missing tables. pom.xml must include spring-boot-starter-flyway and flyway-mysql; Boot 4 does not auto-run flyway-core alone, so a tree with only flyway-core will leave users/products missing. Do not set baseline-on-migrate true over leftover flyway_schema_history. Do not add flyway-maven-plugin; starter-flyway migrates at runtime and a plugin version clash is a hard failure. Do not hardcode a datasource password in application.yml. Before any Final Answer, the tree must contain REST *Controller.java classes with @RestController, Flyway SQL under src/main/resources/db/migration for users, products, inventory, orders, and order_items, static HTML under src/main/resources/static, application.yml or application.properties that reads SPRING_DATASOURCE_* from the environment, src/test/java *Test.java, and project-local Maven (an unpacked .tools/apache-maven-3.9.16 or a wrapper that already contains bin/mvn.cmd; a download-only mvnw that fetches into the user home is a hard failure). MYSQL_URL, MYSQL_USER, MYSQL_PASSWORD, MYSQL_ADMIN_PASSWORD, APP_ADMIN_USERNAME, APP_ADMIN_PASSWORD, T09_ADMIN_PASSWORD, SPRING_DATASOURCE_URL, SPRING_DATASOURCE_USERNAME, and SPRING_DATASOURCE_PASSWORD are already injected into the process environment for a temporary least-privilege schema; read those values from the environment and never print, log, or write the password. Seed the demo admin from APP_ADMIN_PASSWORD or T09_ADMIN_PASSWORD; MYSQL_ADMIN_PASSWORD is the database password, not the demo login. Database URL, username, password, and demo admin password must come from environment variables and must never be written to source, README, prompt, logs, or Git. Use Flyway for users, products, inventory, orders, and order_items with migration and rollback documentation. Implement REST backend and static frontend with login, session authentication, logout, product CRUD, inventory CRUD, transactional order stock decrement, low-stock alerts, and date-filtered revenue admin console. Run Maven unit/integration tests and API smoke tests and write real counts into TEST-REPORT.md; placeholders such as 待填写, 待执行, 待验证, or 若干 are a hard failure. TEST-REPORT.md must quote an actual Maven line with Tests run: N, Failures: 0, Errors: 0. Quoting Failures: N>0, Errors: N>0, or <<< FAILURE! is a hard failure even if Tests run: N is present. MYSQL_* is already injected, so do not skip mvn test. Really perform login, logout, product edit, order, stock change, and revenue update. Use only a temporary schema and least-privilege user; if MySQL 8, the specified Maven, or SHA-512 verification is unavailable, record unavailable instead of silently substituting an in-memory database. Deliver README.md, DEVELOPMENT.md, API.md, ARCHITECTURE.md, SECURITY.md, MIGRATION-ROLLBACK.md, and TEST-REPORT.md, plus schema/user cleanup proof. Write README.md, DEVELOPMENT.md, API.md, ARCHITECTURE.md, SECURITY.md, and MIGRATION-ROLLBACK.md with the write tool as soon as pom.xml, Controller.java, Flyway SQL, and static HTML exist; do not wait for Maven download. Write TEST-REPORT.md after mvn test with the actual Tests run: N, Failures: 0, Errors: 0 line. ${commonRules}`
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

export function parseMissingFilenames(error: string): string[] {
  const match = error.match(/missing\s+([^;]+)/i)
  if (match !== null) {
    return match[1]
      .split(/,| and /i)
      .map((name) => name.trim().replace(/[.;]+$/g, ''))
      .filter((name) => {
        if (name.length === 0) return false
        if (/^spring-boot-starter-/i.test(name)) return false
        return /\.(md|java|html|xml|yml|yaml|properties|sql|csv|js|css)$/i.test(name) || name.includes('/') || name.includes('\\')
      })
  }
  if (/no src\/test\/java/i.test(error)) {
    return ['src/test/java/com/rxycode/t09coffee/CoffeeApplicationTest.java']
  }
  if (/no static frontend HTML/i.test(error)) {
    return ['src/main/resources/static/index.html']
  }
  if (/Flyway SQL/i.test(error)) {
    return ['src/main/resources/db/migration/V1__init.sql']
  }
  if (/no application\.(yml|yaml|properties)/i.test(error)) {
    return ['src/main/resources/application.yml']
  }
  return []
}

function t09ControllerDir(rels: string[]): string {
  const app = rels.find((file) => /Application\.java$/i.test(file) && /(^|\/)src\/main\/java\//i.test(file))
  if (app !== undefined) return app.replace(/\/[^/]+$/, '/controller')
  return 'src/main/java/com/coffee/controller'
}

export function selectMissingFileRepair(scenarioId: string, error: string, files: string[]): string[] {
  const parsed = parseMissingFilenames(error)
  const rels = files.map((file) => file.replace(/\\/g, '/'))
  const hasIndex = rels.some((file) => /(^|\/)index\.html$/i.test(file))
  if (scenarioId === 'T03') {
    // A missing-file stub that rewrites index.html is how T03-3 went false-green.
    // Docs and a missing admin.html on an already-written site should still use write-now repair.
    if (!hasIndex) return []
    const docs = parsed.filter((name) => /\.md$/i.test(name))
    const other = parsed.filter((name) => !/\.md$/i.test(name))
    const disallowed = other.filter((name) => !/^admin\.html$/i.test(name))
    if (disallowed.length > 0) return []
    const needed = [...docs]
    const hasAdmin = rels.some((file) => /(^|\/)admin\.html$/i.test(file))
    if (!hasAdmin) needed.push('admin.html')
    return needed
  }
  if (scenarioId === 'T09') {
    if (/starter-flyway|H2\/SQLite|jdbc:h2/i.test(error)) return []
    if (/mvn test failed|Downloading Maven|no project-local Maven|PluginContainerException|mysql schema reset/i.test(error)) return []
    const docs = parsed.filter((name) => /\.md$/i.test(name))
    const hasController = rels.some((file) => /Controller\.java$/i.test(file))
    const hasStatic = rels.some((file) => /\/resources\/static\/.+\.html$/i.test(file) || /(^|\/)index\.html$/i.test(file))
    if (/no \.java source|hyphen directory|T09_coffee instead|output directory was not created/i.test(error)) {
      const dir = t09ControllerDir(rels)
      return [
        'pom.xml',
        ...['Auth', 'Product', 'Inventory', 'Order', 'Revenue'].map((name) => `${dir}/${name}Controller.java`),
        'src/main/resources/application.yml',
        'src/main/resources/db/migration/V1__init.sql',
        'src/main/resources/static/index.html',
        'src/test/java/com/coffee/CoffeeApplicationTest.java'
      ]
    }
    if (/do not start Spring|class-load|or MockMvc|empty contextLoads/i.test(error)) {
      const tests = rels.filter((file) => /(^|\/)src\/test\/java\/.+Test\.java$/i.test(file))
      return tests.length > 0 ? tests : ['src/test/java/com/coffee/CoffeeApplicationTest.java']
    }
    if (/no \*Controller\.java/i.test(error) && !hasController) {
      const dir = t09ControllerDir(rels)
      const needed = ['Auth', 'Product', 'Inventory', 'Order', 'Revenue'].map((name) => `${dir}/${name}Controller.java`)
      if (!hasStatic) needed.push('src/main/resources/static/index.html')
      if (!rels.some((file) => /\/db\/migration\/.+\.sql$/i.test(file))) {
        needed.push('src/main/resources/db/migration/V1__init.sql')
      }
      if (!rels.some((file) => /(^|\/)src\/test\/java\/.+Test\.java$/i.test(file))) {
        needed.push('src/test/java/com/coffee/CoffeeApplicationTest.java')
      }
      return needed
    }
    if (docs.length > 0 && hasController) {
      const names = docs.filter((name) => /\.md$/i.test(name))
      if (/harness mvn test observed:/i.test(error) && !names.some((name) => /^TEST-REPORT\.md$/i.test(name))) {
        names.push('TEST-REPORT.md')
      }
      return names
    }
    if (/harness mvn test observed:[\s\S]*Failures:\s*0,\s*Errors:\s*0/i.test(error) && hasController) {
      return ['TEST-REPORT.md']
    }
    if (/no real Maven test counts|placeholders|records Failures|records Errors/i.test(error) && hasController && !/mvn test failed/i.test(error)) {
      return ['TEST-REPORT.md']
    }
    return parsed
  }
  if (scenarioId === 'T04' || scenarioId === 'T06' || scenarioId === 'T07' || scenarioId === 'T08') {
    // T04-1 wrote a three-file index/README/TEST-REPORT stub after a cancelled recovery.
    if (!hasIndex) return []
    return parsed.filter((name) => /\.(md|csv)$/i.test(name))
  }
  return parsed
}

export function buildSpringMysqlRepairInstructions(validationError: string): string {
  const mandatory = 'Java 17 + Maven pom.xml + Spring Boot + Flyway are mandatory. A Python, Flask, Django, or SQLite substitute is a hard failure. Keep existing *Controller.java wherever they already are; any package under src/main/java is valid. Do not rename packages or relocate controllers to com.rxycode.t09coffee.web.'
  if (/hyphen directory|T09_coffee instead|no \.java source|output directory was not created/i.test(validationError)) {
    return `${mandatory} The required directory is T09-coffee with a hyphen. T09_coffee is a hard failure. Call the write tool now for pom.xml, Auth/Product/Inventory/Order/Revenue *Controller.java, Flyway SQL, src/main/resources/static/index.html, application.yml, and an @SpringBootTest MockMvc *Test.java under T09-coffee/. Do not probe MySQL. Do not write _probe files. Do not use bash until those files exist.`
  }
  if (/mvn test failed|produced no Tests run/i.test(validationError)) {
    return `${mandatory} Compiler or test errors are listed in the validation failure. Do not rewrite the whole tree and do not relocate packages. Edit only the files named in [ERROR] lines. If a symbol is missing, write that class in the same package or stop calling it; Optional.orElseThrow belongs on Optional, not on the entity. Inventory is a separate table/entity: do not call Product.getInventory() unless that association exists; save Inventory through InventoryRepository. Money must be java.math.BigDecimal; stock quantities must be int or Integer; do not assign double to Integer or BigDecimal. If com.fasterxml.jackson.databind.JsonNode or ObjectMapper cannot be found, this is Boot 4 Jackson 3: import tools.jackson.databind.JsonNode and tools.jackson.databind.ObjectMapper, or drop JsonNode and use jsonPath; do not add jackson-databind 2. If AutoConfigureMockMvc is missing from org.springframework.boot.test.autoconfigure.web.servlet or org.springframework.boot.test.autoconfigure.webmvc, this is Spring Boot 4.1: add spring-boot-starter-webmvc-test with test scope and import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc. Then run project-local mvn test again until Failures: 0, Errors: 0 and write TEST-REPORT.md quoting that line. Do not quote Errors: N>0 or <<< FAILURE! as success. If DaoAuthenticationProvider has no no-arg constructor or no setUserDetailsService, this is Spring Security 7 / Boot 4: use new DaoAuthenticationProvider(userDetailsService) then setPasswordEncoder, or delete the provider bean and let Boot wire UserDetailsService plus PasswordEncoder. If a table does not exist, Spring Boot 4.1 did not run Flyway: add spring-boot-starter-flyway (flyway-core alone is not enough), keep flyway-mysql, put CREATE TABLE users/products/inventory/orders/order_items in classpath:db/migration, and do not baseline-on-migrate over dirty history. If login or MockMvc returns Status expected:<200> or <201> but was:<403>, CSRF is blocking JSON POSTs: call csrf.disable() or ignoringRequestMatchers("/api/**"); do not keep CookieCsrfTokenRepository unless the test uses spring-security-test csrf(). Do not parse Set-Cookie by hand. If Status expected:<200> or <201> but was:<401>, AuthenticationManager is not authenticating: expose a ProviderManager(daoAuthenticationProvider) @Bean and do not build it from http.getSharedObject(AuthenticationManagerBuilder). After login, later mockMvc.perform() calls must reuse .session(loginResult.getRequest().getSession()); a new perform() starts an empty session. If admin already exists, DataSeeder must still re-encode and save the password the test uses. If Status expected:<200> but was:<400> on login, login failure was mapped to 400: return 401 for BadCredentialsException and do not @ExceptionHandler(IllegalArgumentException) onto /api/auth/login. Tests must POST the same username/password DataSeeder creates; do not login as barista unless that user is seeded. If admin already exists, re-encode and save the password from T09_ADMIN_PASSWORD so it matches the test. If a product POST is 400, send the @Valid fields (name, BigDecimal price) as JSON numbers. If login or MockMvc returns 500 with ROLE_ADMIN cannot start with ROLE_, store the authority as ADMIN and call roles() (which adds ROLE_), or call authorities() with the full name; do not do both. If the failure is PluginContainerException, ClassRealm, or flyway-maven-plugin, delete flyway-maven-plugin from pom.xml; Spring Boot starter-flyway already migrates and the harness resets the test schema. Do not add flyway-maven-plugin, do not bind a Flyway Maven goal to process-test-resources, and do not set baseline-on-migrate. If FlywayValidateException, checksum mismatch, or Found non-empty schema appears, do not set baseline-on-migrate and do not CREATE TABLE from DataSeeder. Leave V1 SQL stable. The harness wipes leftover tables before smoke. Set jpa.hibernate.ddl-auto=none or update, not validate, until Flyway has created the tables. application.yml must read SPRING_DATASOURCE_* from the environment with no hardcoded password fallback. If 找不到符号 names LocalDateTime or similar, add the java.time import; do not rewrite controllers. If 从lambda 表达式引用的本地变量必须是最终变量, copy that local into a final variable before the lambda and edit only the named Java file. If Statement.executeQuery() cannot issue statements that do not produce result sets, JdbcTemplate.query or queryForObject was used for INSERT/UPDATE: use jdbc.update() plus GeneratedKeyHolder or SELECT LAST_INSERT_ID(); do not queryForObject an INSERT. If *Test.java is only contextLoads without mockMvc.perform, add @AutoConfigureMockMvc and at least one API perform() call. Flyway must run before any DataSeeder SQL: use ApplicationRunner or @DependsOn("flyway"), and jakarta.annotation.PostConstruct (not javax). Do not cast HttpSession to MockHttpSession. If Status expected:<200> but was:<500> on PUT /api/inventory, set Inventory.updatedAt before the first save (DATETIME NOT NULL rejects a null insert), load Inventory.product EAGER or map the DTO inside @Transactional, and do not @ExceptionHandler(Exception.class) into HTTP 500 (that hides Caused by). If Unable to find a @SpringBootConfiguration, put *Test.java in the same package as @SpringBootApplication or set @SpringBootTest(classes=TheApplication.class); delete a second test under com.rxycode.t09coffee that cannot see com.rxycode.coffee.CoffeeApplication. Session login is form username/password params plus .session(); do not assert $.token unless login returns a JWT. Do not use MYSQL_ADMIN_PASSWORD as the demo login password. If context load fails with JacksonProperties, SerializationFeature, or No enum constant tools.jackson.databind.SerializationFeature.write-dates-as-timestamps, Spring Boot 4.1 uses Jackson 3: delete spring.jackson.serialization.write-dates-as-timestamps from application.yml, or set WRITE_DATES_AS_TIMESTAMPS: false (uppercase). Do not keep the kebab-case key.`
  }
  if (/SpringBootConfiguration/i.test(validationError)) {
    return `${mandatory} Unable to find @SpringBootConfiguration: *Test.java must live in the same package as @SpringBootApplication or use @SpringBootTest(classes=TheApplication.class). Delete a second test under com.rxycode.t09coffee if the app is com.rxycode.coffee. Session login is form username/password params plus .session(); do not assert $.token unless login returns a JWT. Then run project-local mvn test.`
  }
  if (/TEST-REPORT|no real Maven test counts|待填写|待执行|待验证|若干|records Failures|records Errors/i.test(validationError)) {
    const observedOk = /harness mvn test observed:[\s\S]*Failures:\s*0,\s*Errors:\s*0/i.test(validationError)
    return `${mandatory} MYSQL_* and SPRING_DATASOURCE_* are already in the process environment; do not skip tests. Do not rewrite Java, Flyway, or static HTML. You must call bash to run project-local mvn test (mvnw.cmd, mvn.cmd, or .tools/apache-maven-*/bin/mvn.cmd -f pom.xml test). Then write TEST-REPORT.md quoting Tests run: N, Failures: 0, Errors: 0. Do not write 待验证, 待执行, 待填写, 若干, Errors: N>0, or <<< FAILURE!. ${observedOk ? 'If the validation failure already contains "harness mvn test observed:" with Failures: 0, Errors: 0, copy that Tests run line verbatim.' : 'If the observed line has Errors: N>0 or Failures: N>0, fix the tests first; do not copy a failing line into TEST-REPORT.md.'}`
  }
  if (/write-dates-as-timestamps|JacksonProperties|SerializationFeature/i.test(validationError)) {
    return `${mandatory} Spring Boot 4.1 uses tools.jackson (Jackson 3). Delete spring.jackson.serialization.write-dates-as-timestamps from application.yml; that kebab-case key is not an enum constant. If ISO dates are needed, set WRITE_DATES_AS_TIMESTAMPS: false (uppercase) or omit the jackson.serialization block. Then run project-local mvn test.`
  }
  if (/fasterxml\.jackson\.databind|tools\.jackson\.databind|cannot import com\.fasterxml/i.test(validationError)) {
    return `${mandatory} Spring Boot 4.1 uses Jackson 3. Replace com.fasterxml.jackson.databind.JsonNode and ObjectMapper with tools.jackson.databind.JsonNode and tools.jackson.databind.ObjectMapper, or drop JsonNode and use jsonPath. Do not add jackson-databind 2. Then run project-local mvn test.`
  }
  if (/boot\.test\.autoconfigure\.webmvc/i.test(validationError)) {
    return `${mandatory} AutoConfigureMockMvc lives in org.springframework.boot.webmvc.test.autoconfigure, not org.springframework.boot.test.autoconfigure.webmvc. Fix the import, add spring-boot-starter-webmvc-test, then run project-local mvn test.`
  }
  if (/H2\/SQLite|jdbc:h2|@ActiveProfiles/i.test(validationError)) {
    return `${mandatory} Tests must use the injected SPRING_DATASOURCE_* / MYSQL_* MySQL 8 schema. Delete the H2 dependency, application-test.yml, and @ActiveProfiles("test"). Do not use MYSQL_ADMIN_PASSWORD as the demo login password. Then run project-local mvn test.`
  }
  if (/starter-flyway/i.test(validationError)) {
    return `${mandatory} Spring Boot 4.1 does not auto-run Flyway from flyway-core. Edit pom.xml to add org.springframework.boot:spring-boot-starter-flyway and keep flyway-mysql. Do not rewrite Java sources. Then run project-local mvn test.`
  }
  if (/no \*Controller\.java/i.test(validationError)) {
    return `${mandatory} Call the write tool now for Auth, Product, Inventory, Order, and Revenue *Controller.java files with @RestController under src/main/java. If controllers already exist in another package, leave them and do not start a second tree.`
  }
  if (/Flyway SQL/i.test(validationError)) {
    return `${mandatory} Call the write tool now for src/main/resources/db/migration/V1__init.sql creating users, products, inventory, orders, and order_items. Do not rewrite Java sources.`
  }
  if (/static frontend HTML/i.test(validationError)) {
    return `${mandatory} Call the write tool now for src/main/resources/static/index.html. It must be a closed HTML page with login, product, inventory, order, and date-filtered revenue UI. No CDN. Do not rewrite Java sources or run mvn test until that file exists.`
  }
  if (/no project-local Maven/i.test(validationError)) {
    return `${mandatory} Install unpacked project-local Maven 3.9.16 as .tools/apache-maven-3.9.16/bin/mvn.cmd. A download-only mvnw that fetches into the user home is a hard failure. Do not rewrite Java sources.`
  }
  if (/incomplete; missing /i.test(validationError)) {
    return `${mandatory} Call the write tool for each missing markdown file named in the validation failure. Do not rewrite Java sources.`
  }
  if (/do not start Spring|MockMvc|class-load/i.test(validationError)) {
    return `${mandatory} Do not rewrite controllers or Flyway. Edit src/test/java *Test.java: use @SpringBootTest and org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc. Add spring-boot-starter-webmvc-test. A test that only checks CoffeeApplication.class.getSimpleName() is a hard failure. contextLoads plus at least one MockMvc API call is required. MYSQL_* is already in the environment. Then run project-local mvn test until Failures: 0, Errors: 0.`
  }
  return `${mandatory} Fix only the validation failure. Do not rewrite the whole tree. application.yml must read SPRING_DATASOURCE_* from the environment. Then run project-local mvn test and rewrite TEST-REPORT.md with the actual Tests run: N, Failures: 0, Errors: 0 line if that is still missing.`
}

export function buildMissingFileRepairPrompt(outputDir: string, files: string[], validationError = ''): string {
  const paths = files.map((file) => `- ${outputDir}/${file}`).join('\n')
  const writesAdmin = files.some((file) => /(^|\/)admin\.html$/i.test(file.replace(/\\/g, '/')))
  const writesControllers = files.some((file) => /Controller\.java$/i.test(file.replace(/\\/g, '/')))
  const writesStatic = files.some((file) => /\/resources\/static\/.+\.html$/i.test(file.replace(/\\/g, '/')))
  const writesTests = files.some((file) => /Test\.java$/i.test(file.replace(/\\/g, '/'))) && !writesAdmin && !writesControllers
  const writesOtherDocs = files.some((file) => /\.md$/i.test(file.replace(/\\/g, '/')) && !/(^|\/)TEST-REPORT\.md$/i.test(file.replace(/\\/g, '/'))) && !writesAdmin && !writesControllers && !writesStatic && !writesTests
  const writesReport = files.some((file) => /(^|\/)TEST-REPORT\.md$/i.test(file.replace(/\\/g, '/'))) && !writesAdmin
  const instruction = writesAdmin
    ? 'Call the write tool once for each path below, immediately. You may read js/admin.js only to copy element IDs, then you must write. A read without a write is a failure. Do not dump files with cat, Get-Content, type, or bash. Do not plan. Do not browse. Do not rewrite index.html.'
    : writesControllers || writesStatic || writesTests
      ? 'Call the write tool once for each path below, immediately. Do not download Maven. Do not rename packages. Do not dump files with cat, Get-Content, type, or bash. Do not plan. Do not browse.'
      : 'Call the write tool once for each path below, immediately. Do not read existing game, HTML, CSS, or Java source. Do not dump files with cat, Get-Content, type, or bash. Do not run node --check or javac. Do not plan. Do not browse.'
  const closing = writesAdmin
    ? 'README.md and TEST-REPORT.md must be real UTF-8 documents covering run steps, demo login, and the checks actually performed. admin.html must be a real admin console (not a filename table) with visible 用户管理, 订单管理, 内容管理, 设置, and 分析 navigation, modules #mod-users #mod-orders #mod-content #mod-settings #mod-analytics, .admin-side nav a[data-module], #logout-btn, and <script src="js/admin.js"> if that file exists. After the writes succeed, call ls, confirm every named file exists, then give a short Final Answer listing only the files written.'
    : writesTests
      ? 'Each *Test.java must be compilable JUnit. Use @SpringBootTest and org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc. Inject MockMvc and call mockMvc.perform(...) for at least login or one API. An empty contextLoads() or getSimpleName() check is a hard failure. After the writes succeed, call ls, confirm every named file exists, then give a short Final Answer listing only the files written.'
    : writesReport
      ? `${writesOtherDocs ? 'README.md, DEVELOPMENT.md, API.md, ARCHITECTURE.md, SECURITY.md, and MIGRATION-ROLLBACK.md must be real UTF-8 documents. ' : ''}TEST-REPORT.md must quote Tests run: N, Failures: 0, Errors: 0. Do not write 待验证, 待执行, 待填写, 若干, Errors: N>0, or <<< FAILURE!. ${/harness mvn test observed:[\s\S]*Failures:\s*0,\s*Errors:\s*0/i.test(validationError) ? `Copy this observed line into the report: ${validationError}` : 'If a Tests run line is in the validation failure, copy it only when it has Failures: 0, Errors: 0; otherwise fix tests first.'} After the writes succeed, call ls, confirm every named file exists, then give a short Final Answer listing only the files written.`
    : writesControllers || writesStatic
      ? [
          writesControllers ? 'Each *Controller.java must be a compilable @RestController class, not markdown.' : '',
          writesStatic ? 'src/main/resources/static/index.html must be a closed HTML page with login, product, inventory, order, and date-filtered revenue UI. No CDN.' : '',
          'After the writes succeed, call ls on that directory, confirm every named file exists, then give a short Final Answer listing only the files written.'
        ].filter(Boolean).join(' ')
      : 'Each write must contain a real UTF-8 document, not a filename table. After the writes succeed, call ls on that directory, confirm every named file exists, then give a short Final Answer listing only the files written.'
  return [
    `Missing-file repair for ${outputDir}. These required files are absent: ${files.join(', ')}.`,
    instruction,
    paths,
    closing
  ].join('\n\n')
}
