# Universal Instruction for Correct, Logical, Drift-Resistant Work (V2.1)

*(Applies equally to humans and models. Follow exactly.)*

---

## Scope & Applicability

**This guide works best for:**
- Project-based work with clear deliverables
- Technical problem-solving (software, engineering, analysis)
- Research and investigation tasks
- Business processes and workflows
- Any goal with measurable outcomes and defined completion

**This guide requires adaptation for:**
- Self-improvement and habit formation (see Domain Adaptation)
- Relationship and interpersonal goals (see Domain Adaptation)
- Creative exploration and artistic work (see Domain Adaptation)
- Health, wellness, and therapeutic processes (see Domain Adaptation)

**Core principles remain universal. Application methods vary by domain.**

---

## Phase I: Strategy & Alignment

### 1. Verify Value and Necessity (The "Why" Gate)

**Before defining the goal, validate that the task is worth doing.**

* Ask: "If I succeed, what is the concrete benefit?"
* Ask: "Is this the simplest way to achieve that benefit?"
* Ask: "What happens if I *don't* do this?" (If the answer is "nothing," **stop immediately**).
* **Constraint:** Do not optimize a process that should be eliminated.

**Examples of tasks to reject:**
- Automating a manual process that happens once per year
- Building a feature no one requested or needs
- Refactoring code that works and won't be touched again
- Perfecting something that's already "good enough"

---

### 2. Define the Goal (Mandatory)

* State the goal in **one clear sentence**.
* Define at least **one measurable or observable success condition**.
* If measurement is not possible, define a **falsification condition** (how failure would be recognized).
* Re-read the goal before every major decision.
* If an action does not clearly advance the goal, **do not perform it**.

**Template:**
- **Goal:** [One sentence describing what success looks like]
- **Success condition:** [How you'll know it worked]
- **Failure condition:** [How you'll know it failed]

---

### 3. Collect and Bound Context Before Acting

**Before making any change:**

* **Review relevant past work FIRST:**
  * Check `/archive/` for similar completed projects
  * Review `/patterns/` for reusable solutions
  * Check `/common-problems/` for known issues and solutions
  * Read `lessons.md` files from related past work
  * Ask: "Have I solved something similar before? What did I learn?"
  * **Time investment:** Spend 10-15 minutes reviewing past context before starting - this often saves hours later

* **Gather all relevant information:**
  * Existing files, notes, prior decisions
  * Constraints, assumptions, dependencies
  * External dependencies (other people, systems, approvals)
  * **Lessons from similar past projects** (what worked, what failed)

* **Explicitly list:**
  * **What is known** (from current context AND past experience)
  * **What is unknown**
  * **What was learned from similar tasks before**

* **Classify context as:**
  * Relevant
  * Possibly relevant
  * Out of scope

* **Map dependencies explicitly:**
  * Which steps depend on other steps (sequential dependencies)
  * Which steps can run in parallel (independent work streams)
  * Which dependencies are external or blocking
  * **Parallel work safety rules:**
    - Only parallelize if steps have NO shared state
    - Define merge strategy before splitting work
    - Validate merged results as a separate step
    - When in doubt, keep work sequential

* **Freeze the working context** before execution begins.
* If new context appears later, pause and revisit the plan.
* If information is missing:
  * Do **not** guess silently
  * Check if similar situations were documented in past work
  * Either obtain it or proceed with **clearly labeled assumptions**

---

### 4. Prime the Environment

**Do not execute in a cluttered state.**

* **Organize the Workspace (Do NOT delete):**
  * **Archive** completed work to designated folders (e.g., `/archive/project-name/`)
  * **Close** (don't delete) browser tabs/files unrelated to current goal
  * **Move** (don't remove) physical objects to storage areas
  * **Keep accessible:** Past project folders, decision logs, and lessons learned
  * **Critical:** Never delete context from completed tasks - you'll need it for future reference

* **Structure for Context Preservation:**
  ```
  /workspace
    /current           - Active work only
    /archive
      /2024-12-project-x
        /docs          - All documentation
        /decisions     - Decision logs
        /lessons.md    - What was learned
        /handoff.md    - Final state
      /2024-11-project-y
        ...
    /patterns          - Reusable solutions from past work
    /common-problems   - How similar issues were solved before
  ```

* **Tool Check:** Ensure all required software, access tokens, or tools are installed and working *before* execution starts.

* **Mental State (Humans):** 
  * Eliminate **active** distractions (notifications, noise, competing tasks)
  * Keep **passive reference materials** accessible (past notes, lessons learned)

* **Context Window (AI):** 
  * Separate **active context** (current task) from **reference context** (past learnings)
  * Clear working memory of unrelated prompts, but maintain access to archived task summaries
  * Before starting new task, briefly review: "What similar problems have I solved before?"

**Quick environment checklist:**
- [ ] Only **current task** files are open in editor
- [ ] All required tools are installed and tested
- [ ] **Past project archives** are accessible but not cluttering workspace
- [ ] No unrelated browser tabs or applications in active view
- [ ] Notifications disabled (humans) or active context focused (AI)
- [ ] Physical workspace organized with storage areas (humans)
- [ ] **Quick reference to past learnings** available (lessons.md, patterns/)

---

## Phase II: Planning & Architecture

### 5. Create a TODO Plan (Non-Optional)

* Break work into **small, atomic steps** (ideally 3–8 per phase).
* **The Recursive Rule (Fractal Planning):**
  * *If a single step is complex, vaguely defined, or estimated to take >2 hours, treat that step as a separate project. Recursively apply this entire guide to that specific step.*
  * Mark recursive steps clearly: `[RECURSIVE]` or `[SUB-PROJECT]`

* **Each step must define:**
  * What will be done
  * Required inputs
  * Expected output
  * Validation method
  * **Estimated effort or time**

* Order steps logically.
* Include validation steps early and often.
* For each critical step, define a **Plan B** (fallback if primary approach fails).

* **Define:**
  * **Completion condition** for the entire plan
  * **Stop conditions** that require pausing or replanning
  * **Time/resource budget** for the overall task
  * **Quality thresholds**: what "good enough" means for this task
    - Critical requirements (must have)
    - Important features (should have)
    - Nice-to-have features (can defer)

* **Mark checkpoint steps** where stable states should be preserved.

**Example TODO structure:**
```
1. [Setup] Configure development environment (30min)
   - Input: Project requirements
   - Output: Working dev environment
   - Validation: Run hello-world test
   - Plan B: Use containerized environment

2. [CHECKPOINT] Implement core feature (2h) 
   - [RECURSIVE - See SUB-TODO-CORE.md]

3. [Validation] Run integration tests (15min)
```

---

## Phase III: Execution & Validation

### 6. Execute One Step at a Time

**For each step:**

1. Confirm prerequisites are satisfied.
2. **Create a rollback point** before risky changes (if applicable).
3. Execute the step.
4. Immediately verify the result.
5. Record:
   * What was done
   * What changed
   * Whether it worked
   * **Actual time/effort spent vs. estimated**

* Never proceed to the next step without verification.
* If time budget is exceeded, **stop and reassess** whether to continue or adjust scope.

**Time tracking benefits:**
- Improves future estimation accuracy
- Reveals bottlenecks early
- Helps detect drift (too much time on non-critical tasks)

---

### 7. Enforce Self-Validation

**After each step and at completion:**

* Validate using at least one of:
  * Tests (automated or manual)
  * Small controlled examples
  * Cross-checks against trusted sources
  * Logical consistency checks

* At least **one validation must be logically independent** from the implementation.
* Rate confidence honestly (0-100%).
* Distinguish between:
  * **Critical validations** (must pass to continue)
  * **Nice-to-have validations** (can be deferred if time-constrained)

* If confidence is low (<80%) or validation fails:
  * Add a corrective step to the TODO list.

* **No validation means the work is incomplete.**

**Independent validation examples:**
- If you wrote code, test it with real data
- If you made a calculation, verify with different method
- If you designed something, get external review
- If you researched something, cross-check multiple sources

---

### 8. Justify All Decisions

* Every decision must be based on:
  * Collected context, or
  * Trusted, verifiable sources

* If something is theoretical, experimental, or unverified:
  * State this explicitly: `[ASSUMPTION]`, `[EXPERIMENTAL]`, `[UNVERIFIED]`

* Do not use undocumented assumptions.

**Document decisions using:**
```markdown
## Decision: [What was decided]
**Rationale:** [Why this choice]
**Alternatives considered:** [Other options]
**Risks:** [Known downsides]
**Source:** [Context or reference]
```

---

## Phase IV: Memory & Maintenance

### 9. Manage Memory Deliberately

**Maintain two types of memory:**

* **Short-term memory:**
  * Temporary facts, intermediate results, current focus
  * Keep in working memory only what's actively needed
  * **Clear after each session or task completion**

* **Long-term memory:**
  * Stable decisions, rules, patterns, lessons learned
  * **Externalize to files** when memory becomes complex or needs persistence

* **Organizational memory (builds over time):**
  * Accumulated knowledge from all past projects
  * Patterns that emerge across multiple tasks
  * Solutions to recurring problems
  * Estimation calibration from historical data
  * **This is your competitive advantage** - you get smarter with each completed task

* **When to externalize memory (move from working memory to files):**
  * Information needed across multiple sessions
  * Complex state that's hard to reconstruct (>5 key facts)
  * Decisions that will affect future work
  * Patterns that apply to multiple projects
  * Any information that takes >30 seconds to re-derive
  * **Solutions that worked well** (add to `/patterns/`)
  * **Problems and their solutions** (add to `/common-problems/`)

* Periodically clean short-term memory (every 1-2 hours or at natural breakpoints).
* Promote information to long-term memory **only if it remains valid after task completion**.
* **Never delete** archived information - compress or reorganize if needed, but preserve it.
* Archive or move memory that no longer affects current decisions, but keep it accessible.

**Memory organization:**
```
/workspace
  /current              - Active work only
  /archive
    /YYYY-MM-project-name
      /docs
      /decisions
      /lessons.md       - Key learnings from this project
      /handoff.md
  /patterns             - Reusable solutions (grows over time)
    /code-patterns.md
    /process-patterns.md
    /decision-frameworks.md
  /common-problems      - Problem-solution pairs
    /debugging.md
    /estimation-errors.md
    /scope-creep.md
  /meta
    /estimation-history.md  - Track estimation accuracy over time
    /retrospectives.md      - Quarterly/yearly self-reviews
```

**Using organizational memory effectively:**
- Before starting any task, spend 10-15 min reviewing relevant past work
- When stuck, check if you've solved similar problems before
- Regularly review patterns to reinforce learning
- Update patterns when you discover better approaches
- Cross-link related projects in documentation

---

### 10. Document Continuously

* Document **while working**, not after.
* Use markdown (`.md`) files to record:
  * Context
  * Plans
  * Decisions and rationale
  * Validation results
  * **Version changes** (what changed, when, why)

* Documentation must allow another person (or future you) to fully reconstruct the reasoning.
* Tag stable states with version markers or checkpoints.

**Maintain a CHANGELOG.md:**
```markdown
## [2024-12-24] - Feature X Implementation

### Added
- Core algorithm for data processing
- Unit tests for edge cases

### Changed
- Refactored input validation (performance improvement)

### Fixed
- Bug in error handling (Issue #42)

### Decisions
- Chose approach A over B due to maintainability
```

**Documentation frequency:**
- Minimum: After each completed step
- Recommended: Every 30 minutes or natural breakpoint
- Critical moments: Before risky changes, after discoveries, at checkpoints

---

### 11. Actively Prevent Drift

* Regularly ask (at least every 3-5 steps):
  > "Does this still serve the original goal?"

* If scope expands:
  * Stop
  * Split new ideas into separate tasks
  * Document them for later

* Finish the current task before starting another.

* **Use a drift detection checklist:**
  * Am I solving the original problem or a different one?
  * Have I added features not in the original goal?
  * Am I optimizing something that doesn't need optimization?
  * Is perfectionism blocking completion?
  * Have I been working on this step for >2x estimated time?
  * Am I researching when I should be executing?

**Common drift patterns to avoid:**
- Gold-plating (adding unnecessary features)
- Analysis paralysis (over-planning)
- Premature optimization
- Scope creep without conscious decision
- Rabbit holes (interesting but irrelevant tangents)

---

### 12. Ask for Guidance When Context Is Insufficient (Mandatory Safety Rule)

* If at any point there is **insufficient context to complete a step safely or correctly**:
  * **Stop execution immediately**
  * Clearly state:
    * What is blocking progress
    * What information is missing
    * What decisions cannot be made without that information

* Actively **ask for guidance or clarification** rather than proceeding under uncertainty.
* **Do not** continue work when the risk of a wrong decision is higher than the cost of asking for help.
* **Deadlock Protocol:** If guidance is not received within a reasonable timeframe (define this based on project urgency: hours for urgent tasks, days for standard work, weeks for long-term projects), explicitly:
  * Switch to Plan B if one exists
  * Document the blocker and archive the task
  * Escalate to stakeholders if this is mission-critical
  * **Never wait indefinitely** - waiting is not working

**Insufficient context indicators:**
- Multiple viable approaches with unclear trade-offs
- Missing requirements or acceptance criteria
- Contradictory information from different sources
- Uncertainty about priorities or constraints
- Lack of domain knowledge for critical decisions

**Reasonable waiting periods by context:**
- **Urgent/blocking work:** 2-4 hours during business hours
- **Standard projects:** 1-2 business days
- **Long-term initiatives:** 1 week
- **Personal projects:** Set your own deadline, then move on

---

### 13. Handle Errors and Recovery

**When an error is discovered:**

* **Stop and assess impact:**
  * Does this affect only the current step or previous work?
  * How far back does the error reach?
  * What downstream work is now invalid?

* **Choose recovery strategy:**
  * **Rollback**: Use checkpoint to restore known-good state
    - When: Error is deep or affects foundations
    - Benefit: Clean slate, no contamination
  * **Patch forward**: Fix in place if impact is isolated
    - When: Error is localized and well-understood
    - Benefit: Preserves other valid work
  * **Restart**: If error is fundamental to approach
    - When: Core assumptions were wrong
    - Benefit: Opportunity to choose better approach

* **Document:**
  * What went wrong
  * Why it went wrong (root cause)
  * How it was fixed
  * What was learned
  * **How to prevent it in the future** (new rule or check)

* Update the TODO plan to prevent similar errors.

**Post-error checklist:**
- [ ] Root cause identified
- [ ] Fix validated independently
- [ ] Similar errors checked elsewhere
- [ ] Prevention rule added
- [ ] Documentation updated

---

## Phase V: Completion & Handoff

### 14. Communicate Progress and Blockers

* **Communicate proactively:**
  * Notify stakeholders when major milestones are reached
  * Report blockers immediately, don't wait
  * Request review before proceeding past critical decision points

* **Escalation triggers:**
  * Blockers that cannot be resolved independently
  * Discoveries that change scope or feasibility
  * Quality issues that put timeline at risk
  * Resource constraints (time, budget, tools)

* Keep communication concise and action-oriented.

**Communication guidelines:**

**Format by context:**
- Quick updates: Chat/Slack (< 2 sentences)
- Progress summaries: Email (< 200 words)
- Complex issues: Document + meeting
- Decisions: Written record + verbal confirmation

**Frequency by project type:**
- Fast-moving: Daily standups
- Standard projects: Weekly updates
- Long-running: Milestone-based + monthly summaries
- Solo work: Document for yourself at natural breakpoints

**Effective update template:**
```markdown
## Status Update - [Date]

**Completed:**
- [Key accomplishment 1]
- [Key accomplishment 2]

**In Progress:**
- [Current focus]

**Blockers:**
- [Issue 1] - Need: [Specific help/decision needed]

**Next Steps:**
- [Planned action]
```

---

### 15. Prepare for Handoff

**If work must be paused or transferred:**

* **Package the current state:**
  * Summary of what's complete (with validation status)
  * Summary of what's pending (prioritized)
  * All context needed to continue
  * Open questions or decisions
  * Location of all relevant files
  * Known issues or risks
  * Environment setup instructions

* **Minimum handoff requirements:**
  * Goal statement and success criteria
  * Current TODO list with status for each item
  * Key decisions and their rationale
  * Known issues or risks
  * Next recommended action (what to do first)
  * Estimated time to resume work

* Document in a single **HANDOFF.md** file for easy discovery.

**HANDOFF.md template:**
```markdown
# Project Handoff - [Project Name]

## Quick Start
**Next Action:** [Immediate next step]
**Estimated Time to Resume:** [X hours/days]

## Goal
[One sentence goal]

## Current Status
**Progress:** [X%] complete
**Last Updated:** [Date]

## What's Complete
- [✓] Item 1 (validated)
- [✓] Item 2 (validated)

## What's Pending
- [ ] Item 3 (high priority)
- [ ] Item 4 (blocked by [reason])

## Key Decisions
1. [Decision] - [Rationale]

## Known Issues
- [Issue 1] - [Workaround]

## Environment Setup
[Prerequisites and setup steps]

## File Locations
- Code: `/src`
- Docs: `/docs`
- Tests: `/tests`

## Context & Background
[Brief explanation of approach and constraints]
```

---

### 16. Reflect and Improve at Completion

**When the task is finished:**

* **Review what worked and what failed:**
  * Which steps went smoothly?
  * Which steps took longer than expected?
  * What unexpected challenges arose?
  * What assumptions were wrong?

* **Extract lessons learned:**
  * What would you do differently?
  * What patterns emerged?
  * What tools or techniques worked well?
  * What should be avoided in the future?

* Convert at least one lesson into a **concrete rule, constraint, or checklist item**.

* **Archive and preserve context for future reference:**
  * Move all project files to `/archive/[project-name]/`
  * Create or update `lessons.md` with key insights
  * Add reusable patterns to `/patterns/` directory
  * Document problem-solution pairs in `/common-problems/`
  * **Do NOT delete** - future you will need this reference

* Update long-term memory and documentation.

* Leave the workspace in a clean, resumable state.

* **Create a completion summary:**
  * Was the goal achieved? (Yes/No/Partial)
  * What were the final validation results?
  * What would you do differently next time?
  * What new knowledge was gained?
  * **Cross-reference with past work:** Did I solve similar problems before? What worked then?
  * **Estimation accuracy review:**
    - Total estimated time: [X hours]
    - Actual time: [Y hours]
    - Accuracy: [X/Y ratio]
    - Biggest estimation misses: [List]
    - Lessons for future estimation: [Key insights]
    - Compare with past projects: Is estimation improving over time?

* **Meta-reflection: "How well did I follow this guide?"**
  * Which steps did I skip or rush?
  * Where did I deviate from the process?
  * Was the deviation justified?
  * Should the guide be updated based on this experience?
  * **Learn from past meta-reflections:** Are the same issues recurring?

* **Build your knowledge base incrementally:**
  * Review `/patterns/` - Can this project contribute new patterns?
  * Review `/common-problems/` - Did I encounter and solve recurring issues?
  * Update your personal "playbook" with refined approaches
  * Note which past projects are most relevant references for future work

**Completion checklist:**
- [ ] All validations passed
- [ ] Documentation complete and up-to-date
- [ ] Lessons extracted and recorded in `lessons.md`
- [ ] Reusable patterns added to `/patterns/`
- [ ] Project archived (not deleted) to `/archive/[project-name]/`
- [ ] Estimation accuracy reviewed and compared with past performance
- [ ] Workspace cleaned but reference materials preserved
- [ ] Handoff document created (if needed)
- [ ] Meta-reflection completed
- [ ] Cross-referenced with similar past projects for pattern recognition

---

## Core Rule (Never Violate)

**Clarity before action. Validation before confidence. Documentation before forgetting.**

---

## Domain Adaptation Guide

**The core principles of this guide are universal, but the application methods must adapt to different domains. Here's how to modify the framework for non-project work:**

---

### Adaptation for Self-Improvement & Habit Formation

**Domain Characteristics:**
- No clear "completion" (ongoing process)
- Success is incremental and long-term
- Emotional and psychological factors dominate
- Consistency matters more than intensity
- Setbacks are normal, not failures

**Key Adaptations:**

**Step 1 (Value Verification):**
- Ask: "Will this improve my life in 6 months? 1 year?"
- Ask: "Am I doing this for myself or to meet others' expectations?"
- Replace "completion benefit" with "directional benefit" (moving toward better, not reaching perfect)

**Step 2 (Define Goal):**
- **Reframe completion as direction:** "Move toward X" instead of "Achieve X"
- **Use process goals, not outcome goals:** 
  - ❌ "Lose 20 pounds"
  - ✅ "Exercise 3x per week for 12 weeks"
- **Success condition:** Sustained behavior change (30-90 days of consistency)
- **Failure condition:** Abandonment without conscious decision

**Step 5 (TODO Plan):**
- **Break into habit layers, not project steps:**
  - Layer 1: Minimum viable habit (5 minutes daily)
  - Layer 2: Sustainable habit (20 minutes 3x/week)
  - Layer 3: Optimized habit (integrated into lifestyle)
- **Recursive rule becomes "90-day rule":** If habit hasn't stabilized in 90 days, treat as separate project to diagnose barriers

**Step 6 (Execute):**
- **Replace "verify result" with "check adherence"**
- **Track streaks and patterns, not completion**
- **Record emotional state and energy levels**

**Step 7 (Validation):**
- **Independence validation:** Ask trusted friend/partner to assess change
- **Behavioral evidence:** Can you demonstrate the skill/habit spontaneously?
- **Integration test:** Does the habit survive disruption (travel, stress, illness)?

**Step 11 (Prevent Drift):**
- **Inverse drift check:** "Am I making this harder than it needs to be?"
- **Perfectionism is the main enemy:** Good enough is actually good enough
- **Allow flexible implementation:** Missing one day is not failure

**Modified Documentation:**
- Keep a **habit journal** instead of technical docs
- Record: triggers, emotional state, what worked, what didn't
- Focus on patterns over individual instances

**Example: Learning a Language**

**Traditional approach (doesn't work):**
```
Goal: Become fluent in Spanish (vague, overwhelming)
Steps: 1. Learn grammar 2. Memorize vocab 3. Practice speaking
Problem: No clear end, too big, easy to abandon
```

**Adapted approach:**
```
Goal: Have 5-minute conversations in Spanish within 6 months

Phase 1 (Months 1-2): Foundation Layer
- Duolingo 10 min daily (streak tracking)
- Learn 5 new words daily (Anki flashcards)
- Watch 1 Spanish show/week with subtitles
Validation: 90% adherence to daily practice

Phase 2 (Months 3-4): Integration Layer
- Join language exchange (1hr/week)
- Think simple thoughts in Spanish (note when it happens naturally)
- Listen to Spanish podcast during commute
Validation: Can introduce myself and hold 2-min conversation

Phase 3 (Months 5-6): Application Layer
- 15-min conversation practice 2x/week
- Write journal entries in Spanish
- Attempt to order food in Spanish at restaurant
Validation: 5-minute conversation with native speaker (recorded for proof)
```

---

### Adaptation for Relationship & Interpersonal Goals

**Domain Characteristics:**
- Another person has agency (you can't control outcomes)
- Success requires mutual agreement on goals
- Emotional safety is prerequisite
- Process matters more than specific achievements
- Over-optimization can damage connection

**Key Adaptations:**

**Step 1 (Value Verification):**
- **Critical addition:** "Does the other person want this too?"
- **Reframe benefit:** "What does success look like for **both** of us?"
- **Discard unilateral improvement goals:** You cannot "fix" another person

**Step 2 (Define Goal):**
- **Co-create the goal:** Both people must agree on what success means
- **Use relationship-quality metrics:**
  - Frequency of positive interactions
  - Conflict resolution effectiveness
  - Mutual satisfaction levels (subjective but valid)
- **Example:**
  - ❌ "Get my partner to communicate better" (unilateral)
  - ✅ "Reduce arguments by improving how we both handle disagreements"

**Step 3 (Context):**
- **Add emotional context:**
  - Current relationship satisfaction (1-10 scale for both)
  - Recent conflicts or tensions
  - Love languages and communication preferences
  - External stressors affecting both people
- **Critical unknown:** The other person's internal experience (you can ask, but cannot assume)

**Step 5 (TODO Plan):**
- **Replace technical steps with interaction patterns:**
  - Experiments, not mandates
  - Time-boxed trials (try for 2 weeks, then reassess together)
  - Focus on behaviors you control, not outcomes
- **Example plan for "Improve connection with partner":**
  ```
  Experiment 1 (2 weeks): Quality time baseline
  - My action: Propose 30-min phone-free time together 3x/week
  - Validation: Ask partner if they feel more connected
  
  Experiment 2 (2 weeks): Appreciation practice
  - My action: Share one specific appreciation daily
  - Validation: Partner reciprocates or expresses feeling valued
  
  Check-in: Jointly assess what's working
  ```

**Step 6 (Execute):**
- **Never execute on partner without consent**
- **Propose, don't implement:** "Can we try X for 2 weeks?"
- **Observe reactions, not just results:** Is partner engaged or resentful?

**Step 7 (Validation):**
- **Joint validation required:** Success is only valid if both people confirm it
- **Subjective measures are legitimate:** "Do you feel more connected?" is valid data
- **Independence check:** Ask a trusted friend if they've noticed positive changes

**Step 10 (Documentation):**
- **Be very careful with documentation in relationships:**
  - ✅ Private journal about your own feelings and observations
  - ✅ Shared notes from couples discussions (with consent)
  - ❌ Tracking partner's "compliance" with plans
  - ❌ Detailed logs that feel like surveillance

**Step 11 (Prevent Drift):**
- **Unique drift pattern:** Over-optimizing can make relationship feel transactional
- **Check:** "Does this feel natural or forced?"
- **Check:** "Am I treating my partner like a project?"

**Step 14 (Communication):**
- **Vulnerable communication, not status updates:**
  - Share feelings, not just facts
  - Use "I feel" statements
  - Create safety for partner to share their truth
- **Regular check-ins:** "How are we doing? What's working? What's not?"

**Critical Warnings for Relationship Goals:**

⚠️ **This framework can be harmful if misused:**
- Do NOT use it to manipulate or control another person
- Do NOT treat your partner as a "system to optimize"
- Do NOT document everything (this destroys trust)
- Do NOT proceed with unilateral "improvement plans"

✅ **Use it appropriately:**
- For self-improvement within the relationship (your own communication, emotional regulation)
- For jointly agreed experiments
- For tracking your own growth and awareness
- For structured reflection on relationship patterns

**Example: Improving Communication with Partner**

**Wrong approach:**
```
Goal: Get partner to open up more
Plan: 
1. Ask more questions
2. Create "safe space"
3. Track frequency of deep conversations
Problem: Treats partner as object to be fixed, no mutual agency
```

**Right approach:**
```
Goal: I want to be a better listener and create more space for vulnerability

Personal work (my responsibility):
1. Notice when I interrupt or give unsolicited advice
2. Practice active listening (reflect back what I hear)
3. Share my own vulnerabilities first (model openness)
Validation: I feel more connected, partner shares more freely

Joint experiment (requires consent):
"I've noticed we've been surface-level lately. Want to try a weekly 
check-in where we share one thing we're struggling with? No advice, 
just listening. We can try for 3 weeks and see if we like it."

Validation (mutual):
- After 3 weeks: "Did this feel helpful to you?"
- Adjust based on both perspectives
- Continue only if both want to
```

---

### Adaptation for Creative & Exploratory Work

**Domain Characteristics:**
- The journey is the destination
- Drift and exploration are often valuable, not wasteful
- Over-planning kills inspiration
- Success is subjective and emergent
- "Completion" may not be meaningful

**Key Adaptations:**

**Step 1 (Value Verification):**
- **Reframe the value question:** "Will this bring joy, growth, or insight?"
- **Allow intrinsic value:** "I want to explore this" is sufficient justification
- **Replace ROI with fulfillment:** Creative work doesn't need external validation

**Step 2 (Define Goal):**
- **Use directional goals, not specific outcomes:**
  - ❌ "Write a novel with 300 pages"
  - ✅ "Explore this character's journey until it feels complete"
- **Success condition:** Personal satisfaction or creative fulfillment
- **Failure condition:** Loss of interest despite giving it genuine effort

**Step 5 (TODO Plan):**
- **Use very loose structure:**
  - Phases, not steps (Exploration → Development → Refinement)
  - Flexible timeboxes ("Spend 2 weeks in exploration mode")
  - Permission to pivot completely
- **Recursive rule relaxed:** Allow long, unstructured exploration phases

**Step 6 (Execute):**
- **Allow undirected exploration time** (30-50% of total time)
- **"Productive drift" is valid:** Following creative tangents is not failure
- **Validation becomes "resonance check":** Does this feel right? Is energy flowing?

**Step 11 (Prevent Drift):**
- **Invert the drift rule:** 
  - "Am I forcing structure where emergence is better?"
  - "Is planning blocking creation?"
- **Useful drift vs. avoidance drift:**
  - Useful: Exploring related ideas that enhance the work
  - Avoidance: Endless planning, research, or tool-switching to avoid creating

**Step 10 (Documentation):**
- **Documentation becomes a creative artifact:**
  - Artist's journal instead of technical log
  - Capture inspirations, not just decisions
  - Allow non-linear, associative notes

**Example: Writing a Novel**

**Too rigid (kills creativity):**
```
Goal: Write 80,000 word novel in 6 months
Plan: 
- Outline entire plot (2 weeks)
- Write 500 words/day
- Complete one chapter per week
Problem: Creativity doesn't work on assembly line
```

**Adapted approach:**
```
Goal: Tell [Character]'s story until it feels complete

Phase 1: Discovery (4-6 weeks, flexible)
- Freewrite character backstory
- Explore key scenes without order
- Let plot emerge from character
- No judgment, just create
Checkpoint: Do I understand who this person is?

Phase 2: Structure (2-4 weeks)
- Identify natural narrative arc from Phase 1
- Rough outline (changeable)
- Note key turning points
Checkpoint: Can I see the shape of the story?

Phase 3: Drafting (12-16 weeks)
- Write daily, quantity over quality
- Allow deviations from outline
- Keep exploration journal for tangents
Checkpoint: First draft exists (any length)

Phase 4: Refinement (as long as needed)
- Let draft sit for 2+ weeks
- Revise with fresh perspective
- Know when "good enough" becomes "diminishing returns"
Validation: Story feels complete to me, beta readers engaged
```

---

### Adaptation for Health, Wellness & Therapeutic Goals

**Domain Characteristics:**
- Professional guidance often required
- Non-linear progress is normal
- Setbacks don't mean failure
- Mind-body connection is critical
- One-size-fits-all approaches often fail

**Key Adaptations:**

**Step 1 (Value Verification):**
- **Mandatory safety check:** "Should this be done with professional support?"
- **For mental health:** Working with therapist > self-directed framework
- **For physical health:** Medical clearance may be required

**Step 2 (Define Goal):**
- **Focus on sustainable wellness, not extreme outcomes:**
  - ❌ "Lose 50 pounds in 3 months"
  - ✅ "Develop sustainable, enjoyable movement habits"
- **Success = improved quality of life**, not numbers on a scale

**Step 5 (TODO Plan):**
- **Start with tiny, sustainable steps** (smaller than you think necessary)
- **Build on what works, discard what doesn't**
- **Expect non-linearity:** Progress → Plateau → Regression → Progress

**Step 7 (Validation):**
- **Holistic validation:**
  - Physical: measurable health markers
  - Mental: mood, energy, stress levels
  - Social: relationships, engagement
  - Behavioral: consistency, not perfection
- **Warning signs to stop:**
  - Obsessive tracking
  - Guilt from "failures"
  - Physical injury or burnout
  - Social isolation

**Step 11 (Prevent Drift):**
- **Primary drift: All-or-nothing thinking**
- **Check:** "Am I being compassionate with myself?"
- **Check:** "Is this making my life better or just more controlled?"

**Critical: This framework is NOT a substitute for therapy, medical care, or professional support.**

---

## Domain Adaptation Summary Table

| Domain | Value Gate | Goal Type | Planning Style | Validation | Drift Risk |
|--------|-----------|-----------|----------------|------------|-----------|
| **Project Work** | ROI / Necessity | Completion-based | Detailed steps | Objective tests | Feature creep |
| **Self-Improvement** | Life improvement | Directional / Process | Habit layers | Sustained behavior | Perfectionism |
| **Relationships** | Mutual benefit | Co-created | Joint experiments | Subjective agreement | Over-optimization |
| **Creative Work** | Fulfillment | Emergent | Loose phases | Resonance / satisfaction | Analysis paralysis |
| **Health/Wellness** | Quality of life | Sustainable practice | Tiny incremental steps | Holistic well-being | All-or-nothing |

---

How to Adapt This Guide for Your Domain
1. Identify your domain characteristics:
Is there a clear completion point? (Finite vs. Ongoing)

Are outcomes objectively measurable? (Data-driven vs. Subjective)

Do you have full control over variables? (Solo execution vs. External agency)

Is the process or outcome more important? (Standardized vs. Emergent)

2. Adjust the rigidity dial:
High structure: Project work, technical tasks, and engineering.

Medium structure: Self-improvement, skill-building, and habit formation.

Low structure: Creative exploration, interpersonal relationships, and wellness.

3. Implement domain-specific behaviors:
For High Structure (Strict Execution):

Phase III (Execution) and Phase V (Validation) are non-negotiable and must be documented for every step.

Prioritize reproducibility; another person should be able to achieve the same result using only your logs.

Drift Detection: Treat any deviation from the goal as a system failure requiring immediate pause.

For Medium Structure (Consistency Focus):

Prioritize Step 9 (Memory Management) to track long-term trends rather than atomic technical successes.

Use Step 5 (TODO Plan) to build "Habit Layers," starting with a minimum viable version of the task.

Validation: Measure success by your adherence rate over time (e.g., 90 days) rather than a single outcome.

For Low Structure (Fluid Execution):

Use Step 11 (Preventing Drift) to distinguish between "avoidance drift" (procrastination) and "productive drift" (discovery).

Replace technical justifications in Step 8 (Justification) with "resonance checks"—does the work feel honest, aligned, or emotionally safe?

Validation: Requires mutual or subjective confirmation; success is emergent and may change the goal itself.

4. Calibrate the Feedback Loop:
Recursive Check: When finishing a sub-project, ensure its specific lessons.md are promoted to your primary /patterns/ folder before closing the parent task.

Meta-Reflection: If the process feels too heavy for the task (high overhead), turn the "rigidity dial" down for the next iteration.

Context Refresh: If a task is paused for more than 48 hours, you MUST re-run Step 3 (Collect and Bound Context) to ensure the environment hasn't changed during the wait.
