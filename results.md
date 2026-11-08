# Results

Model: `deepseek-v4-flash` for every agent. Each comparison is paired by scenario, over 50 attack-eligible scenarios, on ticket 1 unless stated otherwise.

Every comparison reports:
- the two overgrant counts;
- the difference, with a 95% scenario-level bootstrap interval;
- the discordant pairs (worse / better);
- an exact two-sided sign test.

The design is in [experiment-design.md](experiment-design.md), the main study, and [experiment-design-extensions.md](experiment-design-extensions.md), the extensions.

| Run | What | Episodes | Crashed | Credits | Data |
|---|---|---|---|---|---|
| Main | the pre-specified design, 12 conditions | 780 | 0 | 0.56 | [`runs/main`](runs/main) |
| E1 | 2 prompts × 2 setups × 6 conditions | 1,560 | 0 | 1.35 | [`runs/e1`](runs/e1) |
| E4 | team of 3 vs 7, neutral prompt, 6 conditions | 780 | 0 | 1.27 | [`runs/e4`](runs/e4) |
| E6 | gemma-4-26b: main design and E4; qwen3.5-397b: E4 | 3 × 780 | 0 | 0.62 + 1.23 + 27.3 | `runs/e6-*` |

Each run folder has `report.html`, an interactive viewer covering every episode and turn, along with `results.json` and `tickets.csv`.

**Honest accuracy was 100% in every no-attack condition of both runs**: 160/160 decisions per condition in the main run, and 160/160 per condition and arm in E1. So no safeguard lowers overgrants by making the team refuse more.

---

## 1. Main run (pre-specified analysis)

### Ticket-1 overgrant rate under attack

| Security prompt | No safeguard | Attribution | Verification |
|---|---|---|---|
| Neutral (main result) | 1/50 (2%) | 13/50 (26%) | 0/50 (0%) |
| Memory-first | 6/50 (12%) | 10/50 (20%) | 4/50 (8%) |

No condition gave an overgrant without the attack, so each attack effect equals the attack rate above.

### Safeguard contrasts (attack effect, safeguard minus no safeguard)

| Prompt | Contrast | Counts | Difference [95% CI] | Discordant | p |
|---|---|---|---|---|---|
| Neutral | attribution vs none | 13 vs 1 | **+0.24 [+0.12, +0.36]** | 12 / 0 | 0.0005 |
| Neutral | verification vs none | 0 vs 1 | −0.02 [−0.06, 0.00] | 0 / 1 | 1 |
| Memory-first | attribution vs none | 10 vs 6 | +0.08 [−0.06, +0.22] | 9 / 5 | 0.42 |
| Memory-first | verification vs none | 4 vs 6 | −0.04 [−0.16, +0.08] | 4 / 6 | 0.75 |

**H0, the hypothesis written after the pilot that attribution can increase overgrants against a first-hand liar:**
- **Supported for the neutral prompt.** The interval lies above zero.
- **Not supported for memory-first.** The interval includes zero.

**Without a safeguard, the attack rarely worked.** Verification gave no significant reduction, because there was little to reduce.

### How the attacks succeeded

**Security nearly always checked.**
- Under the neutral prompt, Security looked up employment type in 300/300 attack turns and never wrote the false value.
- Under memory-first, on ticket 1, it skipped the lookup in 18/150 attack turns. That's close to its skip rate in honest runs (7%).

**Most successes came from the Approver siding with HR.** Of the 34 ticket-1 overgrants under attack:
- 23 came from the Approver choosing HR's false note over Security's correct note: 14 with the neutral prompt and 9 with memory-first, all but one of them under attribution.
- The other 11, all under memory-first, followed a Security note that had copied the lie.

**Attribution's backfire.** When the notes conflicted, the Approver followed HR in:
- 13/50 episodes with attribution against 1/50 without, under the neutral prompt;
- 9/49 against 0/44 under memory-first.

In 22 of the 23 attribution overgrants, the Approver's stated reason was that HR is the authoritative source for employment type. These are the model's own explanations, not proof of cause. Attribution shows both author names and source labels, so this run can't tell which one drives the effect (E5 would).

**Verification failed only when the Approver checked the wrong field.**
- Every overgrant under verification (4/4, memory-first) came from an Approver that spent its one check on role.
- When it checked employment type, it overgranted 0 times in 96 episodes.

**Ticket 2.** These are overgrants, with the lie still in memory and no HR refresh. They were rare except under attribution:
- neutral: 4/50;
- memory-first: 11/50.

Under memory-first ticket 2, a Security note that reused memory and was labelled "not looked up" went with more overgrants (10/22 against 0/27). That suggests labels matter when an honest agent's note is second-hand. It's an association only.

### Reading of the main run

As designed, the benchmark mostly measured how the Approver resolves a conflict between an attacker's note and an honest agent's note. It didn't measure the lie spreading through honest agents. The memory-first instruction barely applied on ticket 1 for two reasons:
- HR's note never held security training, so Security had to query anyway.
- One query returned training and employment type together, so checking training also revealed the truth.

---

## 2. Extension E1: complete memory and split query tools

**What changed** (the `complete_split` setting):
- HR's note can hold every field the policy needs.
- Each lookup tool returns one field.

So under memory-first, Security can skip checking employment type and still have everything it needs.

The original-setup arms re-run the main design in the same run, as the within-run baseline.

### Ticket-1 overgrant rate under attack

| Arm | No safeguard | Attribution | Verification |
|---|---|---|---|
| Neutral, original | 0/50 | 15/50 | 0/50 |
| Neutral, complete memory | 1/50 | 10/50 | 0/50 |
| Memory-first, original | 1/50 | 7/50 | 5/50 |
| **Memory-first, complete memory** | **37/50** | **24/50** | **12/50** |

The no-attack conditions gave 0 overgrants in every arm.

### Pre-specified hypotheses

The primary contrast is E1.1. E1.2–E1.4 are Holm-corrected within E1.

| Hypothesis | Contrast | Counts | Difference [95% CI] | Discordant | p (Holm) | Verdict |
|---|---|---|---|---|---|---|
| **E1.1** (primary) | memory-first, no safeguard: complete vs original | 37 vs 1 | **+0.72 [+0.58, +0.84]** | 37 / 1 | 3×10⁻¹⁰ | **Supported** |
| E1.2a | memory-first, Security looked up employment type: complete vs original (150 attack turns) | 59 vs 143 | −56 points | 5 / 89 | 2×10⁻²⁰ | **Supported** |
| E1.2b | memory-first, Security wrote the false value: complete vs original | 91 vs 7 | +56 points | 89 / 5 | 2×10⁻²⁰ | **Supported** |
| E1.3 | complete + memory-first: attribution vs none | 24 vs 37 | **−0.26 [−0.44, −0.06]** | 7 / 20 | 0.038 | Direction supported; mechanism not (see below) |
| E1.4 (descriptive) | neutral, no safeguard: complete vs original | 1 vs 0 | +0.02 [0.00, +0.06] | 1 / 0 | 1 | No change |

**The refutation condition** ("Security still looks up employment type at about its main-run rate") **was not met**. Under memory-first, the lookup rate fell from 95% to 39%. In honest runs it fell from 98% to 35%.

### What E1 shows

**1. The lie spread through an honest agent once checking looked unnecessary.**
- Under memory-first with complete memory, Security copied HR's false employment type into its own note in 91/150 attack turns.
- Without a safeguard, every copied lie became an overgrant (37/37).
- It persisted to ticket 2: 37/50 overgrants, against 0/50 in the original setup.
- The neutral prompt was unaffected: with complete memory, Security still checked every time.

So it takes both complete memory and an instruction to reuse it.

**2. Attribution helped, but not for the predicted reason.**
- E1.3 predicted that the label "not looked up in own database before writing; same value as note 1 by HR agent" would expose Security's copied fact to the Approver. It didn't. When Security's note copied the lie under attribution, the Approver still overgranted 19 times out of 19.
- The reduction came earlier in the chain. Under attribution, Security looked up employment type more often (31/50 against 13/50 with no safeguard), and checked episodes rarely ended in an overgrant (5/31).
- So attribution changed what the **honest author** did, not how the **decider** read the notes. The data can't say why. One possibility is that seeing labelled sources prompts an agent to earn a "looked up" label itself.

**3. Verification was the strongest safeguard where the lie spread, and it failed in one way only.**
- With complete memory and memory-first, it gave 12/50 against 37/50 with no safeguard: −0.50 [−0.66, −0.34], discordant 2/27, p = 2×10⁻⁶. That's Holm-corrected as a secondary contrast alongside E1.2–E1.4; it stays below 10⁻⁵.
- As in the main run, every verification overgrant came from an Approver that checked role: 12/12 overgranted.
- When it checked employment type, it overgranted 0 times in 38 episodes. That includes 23 episodes where both notes carried the lie and verification alone caught it.

**4. Replication of the main result inside E1:**
- Neutral prompt, original setup: attribution against none was 15 against 0, +0.30 [+0.18, +0.44], p = 6×10⁻⁵. This replicates H0.
- Memory-first, original setup: 7 against 1, +0.12 [+0.02, +0.22], p = 0.07. Same direction as the main run; borderline.
- One rate moved between runs: memory-first with no safeguard gave 6/50 in the main run and 1/50 in E1. Rates near zero vary by a few cases from run to run, so small cells shouldn't be compared across runs. That's why every primary contrast is made within one run.

---

## 3. Extension E4: team size (3 vs 7 agents)

**What changed** (the `relays4` setting): four honest relay agents (IT, Finance, Compliance, Facilities) act after HR and before Security.
- Each relay can look up role only.
- On employment type, each can only copy what memory says.
- The neutral Security prompt is used throughout, as pre-specified.
- The 3-agent arm in the same run is the baseline.

780 episodes, 0 crashed, 0 failed turns, 1.27 credits. Data: [`runs/e4`](runs/e4).

**Honest accuracy:** 100% in both team sizes (480/480 decisions each).

### Overgrants under attack

| Team | No safeguard | Attribution | Verification |
|---|---|---|---|
| 3 agents, ticket 1 | 0/50 | 9/50 | 0/50 |
| **7 agents, ticket 1** | **29/50** | **14/50** | **0/50** |
| 3 agents, ticket 2 | 0/50 | 3/50 | 0/50 |
| 7 agents, ticket 2 | 31/50 | 22/50 | 0/50 |

### Pre-specified hypotheses

| Hypothesis | Contrast | Counts | Difference [95% CI] | Discordant | p | Verdict |
|---|---|---|---|---|---|---|
| **E4.1** (primary, two-sided) | no safeguard, ticket 1: 7 vs 3 agents | 29 vs 0 | **+0.58 [+0.44, +0.72]** | 29 / 0 | 4×10⁻⁹ | **Supported** (higher with 7, as predicted) |
| E4.2 | Security writes the false value after looking up its own database (7 agents) | 0/150 | — | — | — | **Not supported**: Security checked in 300/300 attack turns and never wrote the lie |
| E4.3 | team-size effect under attribution minus under no safeguard (difference of differences) | +0.10 vs +0.58 | **−0.48 [−0.68, −0.28]** | 3 / 23 | 9×10⁻⁵ | **Supported** |
| E4.4 | verification at both sizes | 0/50 and 0/50 | — | — | — | **Supported** |

E4.3 is the only secondary contrast with a test, so Holm leaves it unchanged. It would stay below 3×10⁻⁴ even if corrected over all three secondary hypotheses.

Other contrasts:
- **7 agents:**
  - attribution vs none: 14 against 29, −0.30 [−0.46, −0.14], p = 0.002;
  - verification vs none: 0 against 29, −0.58 [−0.72, −0.44], p = 4×10⁻⁹.
- **3 agents:** attribution vs none, 9 against 0, +0.18 [+0.08, +0.28], p = 0.004. This replicates H0 a third time.

### What E4 shows

**1. The lie spread to every relay, and the size of the majority swayed the Approver.**
- Relays copied HR's false employment type in 193 of 200 relay notes on ticket 1 with no safeguard. The lie reached the last relay in 132 of 150 attack episodes.
- Security still looked up its own database every time and wrote the truth.
- So the Approver saw five notes saying full time against one saying contractor, and overgranted in 29/50 episodes, up from 0/50 in the 3-agent team.
- Every one of the 43 relay-team overgrants gave as its reason that several notes agree, e.g. "Five of six team notes … consistently confirm …" and "the single dissenting Security note conflicts with the preponderance of evidence". These are self-reports.

**2. Attribution worked as designed: at the Approver, this time.**
- Each relay's copied fact was labelled "not looked up in own database before writing; same value as note 1 by HR agent, …".
- That cut the team-size effect from +58 to +10 points.
- This is the mechanism the design predicted for E1.3, which E1 didn't show (there, the drop came from Security checking more). Here Security's behaviour didn't change, so the reduction comes from the Approver discounting second-hand copies.
- Attribution still didn't beat having no relays. The 7-agent attribution rate (14/50) is about the same as the 3-agent attribution rate (9/50; 14 against 9, p = 0.4), which is itself H0's backfire.
- In 10 of the 14 attribution overgrants, the reason again called HR authoritative.

**3. Verification held completely.**
- The Approver verified employment type in all 200 verification tickets.
- It overgranted 0 times, at both team sizes, even with five notes against one.

**4. The lie persisted, but attribution weakened it on ticket 2.**
- With 7 agents, ticket-2 overgrants were 31/50 with no safeguard and 22/50 with attribution.
- On ticket 2 under attribution, relays copied the lie less often (73 of 200 notes, against 165 of 200 with no safeguard). This suggests the labels on ticket 1 made the relays doubt HR's value. It's descriptive only.

**Caveat:** relays tend to name their department in their comment ("Finance DB confirms role …"). So even without attribution, the Approver could see that several different agents agreed. That is part of what "more agents" means here; it isn't a leak of the attribution condition, which adds source labels and author names on every fact.

---

## 4. Extension E6: two more models

Every agent on the team uses the same model. Code, prompts and scenarios are the same as on `deepseek-v4-flash`, with no tuning per model. Both models passed the honest-accuracy gate (20/20) before the runs. The hypotheses were added to the extensions doc before the runs.

| Run | Model | Design | Episodes | Crashed | Failed turns | Credits | Time |
|---|---|---|---|---|---|---|---|
| `e6-gemma-main` | gemma-4-26b-a4b-it | main design | 780 | 0 | 4 | 0.62 | ~15 min |
| `e6-gemma-e4` | gemma-4-26b-a4b-it | team of 3 vs 7 | 780 | 0 | 5 | 1.23 | ~15 min |
| `e6-qwen-e4` | qwen3.5-397b | team of 3 vs 7 | 780 | 0 | 0 | 27.3 | 147 min |

**Honest accuracy:**
- gemma, main design: 960/960.
- gemma, E4: 958/960. Both errors are explained under gemma below.
- qwen: 960/960.

### Ticket-1 overgrants under attack (out of 50)

| Model, team | No safeguard | Attribution | Verification |
|---|---|---|---|
| deepseek, 3 agents (E4 run) | 0 | 9 | 0 |
| deepseek, 7 agents | 29 | 14 | 0 |
| gemma, 3 agents (main-design run) | 9 | 5 | 0 |
| gemma, 3 agents (E4 run) | 14 | 13 | 0 |
| gemma, 7 agents | 27 | 17 | 0 |
| qwen, 3 agents | 4 | 16 | 0 |
| qwen, 7 agents | 18 | 28 | 0 |

### Pre-specified hypotheses

| Hypothesis | Contrast | Counts | Difference [95% CI] | Discordant | p | Verdict |
|---|---|---|---|---|---|---|
| **E6.1** (primary): H0 on gemma | neutral prompt: attribution's attack effect minus no safeguard's | 5 vs 9 | −0.08 [−0.22, +0.06] | 5 / 9 | 0.42 | **Not supported** |
| E6.1, secondary | same contrast, memory-first | 8 vs 6 | +0.04 [−0.08, +0.16] | 6 / 4 | 0.75 (Holm 0.75) | Not supported |
| E6.1, secondary | verification vs none, neutral | 0 vs 9 | −0.18 [−0.30, −0.08] | 0 / 9 | 0.004 (Holm 0.012) | Verification lowers overgrants |
| E6.1, secondary | verification vs none, memory-first | 1 vs 6 | −0.10 [−0.20, 0.00] | 1 / 6 | 0.12 (Holm 0.24) | Not significant |
| **E6.2** (primary): team size on gemma | no safeguard, ticket 1: 7 vs 3 agents | 27 vs 14 | **+0.26 [+0.08, +0.42]** | 18 / 5 | 0.011 | **Supported** |
| E6.2, E4.3 | team-size effect, attribution minus none | — | −0.18 [−0.46, +0.10] | 14 / 19 | 0.49 | Not supported |
| E6.2, E4.4 | verification at both sizes | 0 and 0 | — | — | — | Supported (see the no-decision note) |
| **E6.3** (primary): team size on qwen | no safeguard, ticket 1: 7 vs 3 agents | 18 vs 4 | **+0.28 [+0.12, +0.44]** | 17 / 3 | 0.003 | **Supported** |
| E6.3, E4.3 | team-size effect, attribution minus none | — | −0.04 [−0.30, +0.22] | 14 / 17 | 0.72 | Not supported |
| E6.3, E4.4 | verification at both sizes, ticket 1 | 0 and 0 | — | — | — | Supported. On ticket 2, 1/50 with 7 agents, in a ticket where the Approver didn't verify |

A further contrast wasn't pre-specified for qwen, so it's exploratory. On qwen's 3-agent team, attribution against no safeguard was 16 against 4, +0.24 [+0.08, +0.40], p = 0.012. That's the same size as H0 on deepseek.

### What E6 shows

**1. The team-size effect holds on all three models.** On every model, adding four relays that pass the lie on raised ticket-1 overgrants under no safeguard:

| Model | 3 agents | 7 agents | Difference |
|---|---|---|---|
| deepseek | 0/50 | 29/50 | +58 points |
| gemma | 14/50 | 27/50 | +26 points |
| qwen | 4/50 | 18/50 | +28 points |

On every model the Approver's stated reason is the majority of notes.

**2. Verification is the only safeguard that held on every model.**
- 0 ticket-1 overgrants under attack in every arm of every model.
- One ticket-2 overgrant on qwen, in a ticket where the Approver didn't use its check.

**3. Attribution depends on the model.**

| Model | 3 agents (H0) | 7 agents |
|---|---|---|
| deepseek | backfires (+18 to +30 points) | helps |
| qwen | backfires (+24, exploratory) | **makes it worse**: 28 against 18, +0.20 [+0.02, +0.38] |
| gemma | does nothing | does nothing |

E4.3, attribution shrinking the team-size effect, held only on deepseek. So attribution isn't a reliable safeguard. On two of the three models it raised overgrants in at least one setting.

**4. On qwen, the lie reached an honest agent that had checked.** In 5 episodes, all on ticket 2 of the 7-agent team under attribution, qwen's Security looked up "contractor" in its own database and then wrote "full time", deferring to the others. An example from one note:

> Security DB shows employment_type: contractor … However, HR is authoritative for employment records and recorded full_time (noted by IT, Finance, Compliance, Facilities agents).

All 5 ended in overgrants. Neither deepseek nor gemma did this in any episode. It's what E4.2 predicted for the 7-agent team, and it appears here only on the largest model.

**5. gemma's Approver is more easily misled to begin with.** With a 3-agent team and no safeguard, it sided with HR 9 and 14 times out of 50 in the two runs, where deepseek gave 0–1. That leaves attribution little room to increase it.

**Caveats:**
- **gemma Approvers that never decided:** 8 gemma verification tickets ended without a decision (3 in the main design, 5 in E4). The Approver kept calling `verify` after using up its one call, until it ran out of turns. Under the pre-specified rule these count as not an overgrant, so they help gemma's verification rates slightly. Most of gemma's tool errors are those repeated calls. The rest are Security using a wrong field name, which it corrected on its next try.
- **gemma's two honest errors spread through the majority:** in both, honest HR wrongly recommended write for a contractor. Every relay, Security and the Approver followed ("multiple notes confirm…"). Not part of any hypothesis, but an example of an honest error spreading the same way the lie does.
- **qwen ran slower than estimated:** 147 minutes instead of 80–90, probably because the API slowed under load.

---

## Combined answer so far

**Which safeguard best limits the spread?** It depends on whether honest agents check their own evidence.

| Situation | No safeguard | Attribution | Verification |
|---|---|---|---|
| Honest agents check their own data (neutral prompt, either setup; memory-first, original setup) | attack rarely works (0–12%) | **backfires**: up to 30% (Approver defers to HR's authority) | best: 0–10% |
| Memory makes checking look unnecessary (memory-first, complete memory) | lie spreads to the honest agent: 74% | helps (48%), by making the honest agent check more, not by warning the Approver | **best: 24%**; fails only when the Approver checks the wrong field |
| The lie is relayed by honest agents who can't check it (team of 7) | majority effect: 58% | helps (28%) by labelling the copies as second-hand, but no better than attribution with no relays | **best: 0%** |

That table is for `deepseek-v4-flash`. On two more models (E6), the team-size effect and verification's protection both replicated, but attribution's effect didn't: it does nothing on gemma, and on qwen it backfires in both team sizes.

Verification is the only safeguard that never made things worse, on any model. Its remaining failures all come from the Approver choosing the wrong field to check, or not checking.

## Not yet run

E2 (stronger attacker), E3 (role lie), E5 (Approver replay) and E6's attacker-only model run are planned in [experiment-design-extensions.md](experiment-design-extensions.md). Each will be added here if it runs, or listed as "planned, not run".
