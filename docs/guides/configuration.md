# Configuration

All settings are stored in `~/.autoapply/config.json` and editable from the **Settings** tab in the dashboard.

## Profile

Your personal information used in applications.

| Setting | Description |
|---------|-------------|
| Full name | Your legal name as it appears on applications |
| Email | Contact email for applications |
| Phone | Contact phone number |
| Location | City and state/country (e.g., "New York, NY") |
| Bio | Short description of yourself — sets the tone for cover letters |
| LinkedIn URL | Your LinkedIn profile URL (optional, used on Greenhouse/Lever forms) |
| Portfolio URL | Your personal website or portfolio (optional) |
| Fallback resume | Path to a pre-made PDF resume used when no AI provider is configured |

## Search Criteria

What jobs AutoApply looks for.

| Setting | Description |
|---------|-------------|
| Job titles | Titles to search for (e.g., "Software Engineer", "Backend Developer") |
| Directly accepted locations | Cities accepted for on-site/hybrid work without relocation conditions; migrated from existing locations |
| Relocation destinations | User-configured countries; any city can be considered, without registering municipalities |
| Country priorities | Optional S/A/B/C/D tiers affect ranking without excluding selected destinations |
| Mobility | Domestic and international relocation availability, conditions and future availability |
| Current residence | Maintained in the profile, independently from destinations and directly accepted locations |
| Remote only | Only show remote positions |
| Financial target | Compare only when amount, currency and payment period are sufficient; missing or incomparable information requires review |
| Include keywords | Prefer jobs containing these words (adds to match score) |
| Exclude keywords | Skip jobs containing these words (e.g., "junior", "intern") |
| Experience levels | Target levels: "mid", "senior", "staff", etc. |

### Professional mobility in the assisted dashboard

Open **Preferências de vagas → Mobilidade profissional**. Choose accepted work modes, review migrated direct locations, set domestic/international relocation availability, add countries and priorities, and describe the conditions that would justify a move. Cities are optional for international relocation. Set an optional availability date and financial target; declare work authorization only for countries where you actually hold it. A saved summary explains the resulting rules. New profiles start with no destination countries; personal destination lists are stored in local configuration, never as application defaults.

Geographic results use five labels: **Localidade diretamente aceita**, **Remoto compatível**, **Oportunidade com realocação**, **Necessita revisão** and **Fora das preferências**. Remote compatibility requires permission to hire and work from the candidate's residence, regardless of the employer's headquarters. A remote vacancy requiring residence in a selected foreign country is conditional on relocation. Unconfirmed residence, ambiguous locations, work authorization, sponsorship, salary, language and start dates produce specific review items. Willingness to relocate never proves immigration eligibility.

Professional compatibility is scored independently. The default ranking adds a small country-priority bonus; users can also sort by professional fit, country priority or need to move. Discovery evaluates and ranks all geographically relevant records before applying the result limit. Outside-preference opportunities remain distinguishable in history. Both configuration APIs reevaluate saved jobs when preferences change, preserving application IDs, status, discovery dates and resume versions. Searchers use country-wide queries rather than requiring city enumeration.

Legacy `locations` and `attendance_cities` migrate into `search_criteria.mobility.direct_locations`; existing countries and relocation preferences are preserved. `mobility` is the authoritative policy, with compatibility mirrors for legacy editors. Financial thresholds never imply a currency conversion, net salary or affordable cost of living. [Lever's official Postings API](https://github.com/lever/postings-api) documents salary ranges; [its developer reference](https://hire.lever.co/developer/documentation) defines payment intervals. Published [Greenhouse pay ranges](https://docs.greenhouse.io/job-board) are preserved for review when payment period or applicable region is unknown.

## Application Answers

Pre-filled answers for common screening questions on Workday, Ashby, and other portals. These are stored in `profile.screening_answers` and used automatically when the bot encounters matching questions.

| Setting | Description |
|---------|-------------|
| Work Authorization | Whether you're authorized to work in the target country (Yes/No) |
| Visa Sponsorship | Whether you need visa sponsorship (Yes/No) |
| Years of Experience | Total years of professional experience (e.g., "5") |
| Desired Salary | Target annual salary (e.g., "150000") |
| Willing to Relocate | Whether you'd relocate for a role (Yes/No) |
| Earliest Start Date | When you can start (e.g., "Immediately", "2 weeks") |

### EEO / Voluntary Disclosures (optional)

These are used for Equal Employment Opportunity forms on Workday and similar portals. All fields are optional — if left blank, the bot skips them.

| Setting | Description |
|---------|-------------|
| Gender | Your gender identity |
| Ethnicity | Your ethnic background |
| Veteran Status | Whether you're a veteran |
| Disability Status | Disability self-identification |

Application answers are configured in **Settings → Application Answers**. During the setup wizard, the core 6 fields (work auth through start date) are available in a collapsible section on the Profile step.

## Bot Settings

How the automation runs.

| Setting | Default | Description |
|---------|---------|-------------|
| Platforms | LinkedIn, Indeed | Which job sites to scan |
| Match score | 75 | Minimum job match score (0-100) — higher means stricter |
| Daily limit | 50 | Maximum applications per day |
| Delay | 45 seconds | Wait time between applications |
| Search interval | 30 minutes | How often to search for new jobs |
| Application mode | Full Auto | How applications are handled (see below) |
| Cover letter template | (empty) | Static cover letter used when no AI provider is configured |

### Application Modes

| Mode | What it does |
|------|-------------|
| **Full Auto** | Finds jobs and applies automatically. No user interaction needed. |
| **Review** | Pauses before each application so you can review the cover letter, edit it, or skip. |
| **Watch** | Same as Review, but opens the browser visibly so you can watch the bot work. |

## Schedule

Run the bot automatically on a schedule instead of starting it manually.

| Setting | Default | Description |
|---------|---------|-------------|
| Enable schedule | Off | Turn the scheduler on or off |
| Days of week | Mon–Fri | Which days the bot should run |
| Start time | 09:00 | When the bot starts (24-hour format) |
| End time | 17:00 | When the bot stops (24-hour format) |

Overnight windows work too (e.g., 22:00 to 06:00). The scheduler only stops bots it auto-started — if you start the bot manually outside the schedule, it won't be interrupted.

## Company Blacklist

A list of companies to always skip. Add company names exactly as they appear on job postings. One per line.

## How Settings Are Saved

Settings save when you click Save in the Settings tab. They're stored as JSON at `~/.autoapply/config.json`.

You can also edit `config.json` directly — changes take effect the next time AutoApply reads the config (on startup or when the bot runs a new search cycle).
