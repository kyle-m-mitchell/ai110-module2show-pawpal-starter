# PawPal+ Project Reflection

## 1. System Design

**3 Core Actions for Users**
- add a pet
- schedule a task for a pet
- view the schedule

**a. Initial design**

- Briefly describe your initial UML design.
**4 objects with interworking relationships, attributes, and methods that logically flow together**
- What classes did you include, and what responsibilities did you assign to each?
**I chose Task, Pet, Owner, and Scheduler. The Task class will be responsible for completing tasks, gathering how long and when the task is due. The Pet class will be responsible for adding tasks to the pet. The Owner class will be responsible for presenting all tasks for pets, calculating the owner's availability and adding pets to the owner's profile. The Scheduler class will be responsible for sorting, filtering, and scheduling tasks. It will also detect conflicts in the schedule, mark tasks complete, and schedule future tasks.**
**b. Design changes**

- Did your design change during implementation? **yes, but due to a typo on me end of things**
- If yes, describe at least one change and why you made it.
**the method: create_next_occurence initially had a typo so the AI flagged it.**
---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?

**time, priority, recurrence, conflicting events**
- How did you decide which constraints mattered most?
**I evaluated its value against the customers needs**
**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.

**By default my scheduler plans *greedily*: it places tasks highest-priority-first and slides any task that conflicts into the next free open slot (`build_plan(strategy="greedy")`). This is fast (O(n log n)) and easy to explain — "the vet visit kept its 8:15 time, the walk moved to 8:35" — but it is not guaranteed to keep the *most* total priority. Two priority-3 tasks that could both fit can be pushed out to protect a single priority-5 task that overlaps them. I added an optional `strategy="optimal"` mode (weighted interval scheduling via dynamic programming) that keeps the maximum total priority, but I left greedy as the default. A second, related tradeoff: all of an owner's pets share one timeline, so a task for one pet can be moved by a conflict on another pet — the owner can only be in one place at a time.**

- Why is that tradeoff reasonable for this scenario?

**A busy pet owner values a plan they can understand and trust more than a mathematically optimal one. Greedy's decisions map to a plain sentence ("higher priority wins, everything else reflows to the next free slot"), a real pet's daily task list is small so the greedy and optimal plans are usually identical, and nothing is ever silently dropped — both moved tasks and genuinely unschedulable tasks are reported with a reason. The optimal mode is still available for the rare tight day when packing really matters.**

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
