# Information ledger

Status: ledger version 1.2. Advisory and read-only, implemented in
`scripts/information.py`. It runs in the validation workflow on every change and
never blocks it.

| Axis | What it answers | Needs | State |
|---|---|---|---|
| Observation base | What does the model rest on, and did a change add to it? | Nothing | Verified by full replay of a production world model |
| Commitment | How much do the claims rule out, in bits? | Optional declared questions and answers | Verified on a hand-annotated slice of that model |
| Currency | How has admitted information held up? | Nothing | Verified by walk-forward test on that model's history |

## What it measures

The ledger is arithmetic over reviewed record structure at Git revisions. It uses no
model call, no wall clock and no interpretation of text. It does not measure truth
or source quality. A passing ledger, like a passing compiler, establishes structure
only.

It reads canonical records and two kinds of recorded judgment the repository already
keeps: model operations (`scripts/model_operations.py`) and completed maintenance
reviews. It writes nothing to the repository.

## Observation base

**Origin.** The thing at the end of a source's declared ancestry: a document, a
simulation run, a conversation. For each source, follow `ancestry.parent_source_ids`
to the sources with no recorded parent, then identify each by the first of:

1. `sha256:` its declared `ancestry.content_sha256`;
2. `uri:` its address, with scheme and host lower-cased and the fragment dropped;
3. `source:` its record ID, including when its title matches another source.

The prefix is the **identity basis** and is reported with every count. The report
retains the `title` bucket with a count of zero for compatibility.

**Stratum.** What kind of thing the origin is, from source `kind`: `observational`
(publication, web), `testimonial` (conversation, interview) or `generated`
(simulation, model, reasoning). It is part of the origin's identity, never a quality
rating.

**Link.** An origin *bears on* a claim when any evidence record of that active claim
cites a source resolving to it. A link says the origin was used, not that it agrees.

**Citation.** One source record cited for one claim. Citations beyond the first with
the same set of terminal origins for the same claim are **repeat citations**.

**Proposition.** Claims the repository has judged `equivalent` through a standing
comparison operation are one proposition; any other claim is its own. The ledger
never decides equivalence. It counts what review recorded, and a superseded
comparison counts for nothing.

**Connectors** are measured apart from claims. A connector has **own origins** when
its evidence reaches an origin neither endpoint claim does.

**Inert material** is evidence and sources no active claim or connector cites.

### Laws

Each is a test in `tests/test_information.py` and was checked on real records.

1. **Deterministic.** The report is a function of the bytes at the stated
   revisions. Reordering records or changing the hash seed gives identical bytes.
2. **Wording is invisible.** Rewriting every statement changes no number.
3. **Repetition is exactly zero.** Another passage from an origin that already bears
   on a claim adds no origin and no link.
4. **Exact attribution.** Each origin is one unit, shared equally by the claims it
   bears on, kept as a rational. Shares sum to the number of origins for the whole
   model and for every partition of it (the Shapley value of coverage).
5. **Entropy-like structure.** For parts A and B, reach is monotone, subadditive and
   submodular, and shared origins are never negative.
6. **No residual.** Every change in a total between two states is explained by a
   verdict on one claim. A step that does not balance is an error.
7. **Chain rule.** The gains of all steps along first-parent history sum to the
   final state.
8. **Unknown is counted, not guessed.** Anything undeclared appears under
   `unmeasured` or `inert` with its count.
9. **No weights.** Class and uncertainty partition the ledger. They are never
   multiplied into a score.

### Reading a change

`delta` compares two states and gives every touched claim one verdict:

| Verdict | Test | Gain |
|---|---|---|
| `new_claim_new_origin` | New claim, at least one origin new to the model | Claim, links, its share of each new origin |
| `new_claim_known_origins` | New claim, every origin already held | Claim and links, no origin |
| `gains_origin` | Existing claim gains an origin | Links, and the origin if new to the model |
| `repeat_citation` | Existing claim gains passages with already cited sets of terminal origins | Citations only |
| `adds_citation` | Existing claim gains a new citation set of terminal origins already linked to it | Citations only |
| `support_withdrawn`, `support_changed` | Existing claim loses origins | Negative |
| `origin_reidentified` | Same source records resolve to another origin | Origins and links move; no loss of standing. A step with nothing else reads `origin_identity_changed` |
| `retired` | Claim leaves the active set | Minus its links and exclusive origins |
| `reassessed` | Class, uncertainty or valid time changed | None |
| `unmeasured_edit` | Statement changed | None, flagged as unmeasurable |

A group that brings previously separate claims together is reported apart, with
whether the folded claims rested on different origins (`adds_origins`: the same
finding from another source) or the same ones. The proposition gain also reflects
splits of earlier groups.

The step also gets one outcome label for sorting. A citations-only gain reads
`adds_citations` when it includes a new citation set of terminal origins, and
`repeat_citations_only` when the sets already appear in earlier citations.
`known_origin_share` is the fraction of the origins a step draws on that the model
already held.

A **review cue** flags a new claim whose word set overlaps an earlier claim's by at
least half (shared words over all words in either) on a shared origin, when review
has not compared the pair. It is a heuristic pointer and never enters a total.

## Commitment

Information is always about a question, so this axis exists only where questions
are declared. The record shapes and their rules are in `docs/Ontology.md`; the
arithmetic shared with the compiler is `scripts/answers.py`.

**Question.** A question may declare an answer `space`: `categorical` with `values`,
or `numeric` with `low`, `high` and `step`. The step is the precision that matters
for the question. It makes every space a finite row of cells, and its **capacity**
is `log2` of the cell count.

**Answer.** A claim may declare `answers`, each naming a `question_id`, the part of
that space it admits and the `evidence_ids` that bound it. A stated range admits
every cell it touches.

**State.** An answer stays admitted unless some other answer is admitted by a
strictly larger set of claims. Claims that can all hold leave their intersection.
Claims that cannot all hold leave what each consistent group allows.

**Bits held** are `log2(cells / admitted cells)`: the divergence of the least
committed state consistent with the claims from the declared space.

**Surprise** of an incoming answer is `log2(admitted before / admitted before ∩
incoming)`, measured against the earlier state alone. The **gain** is the difference
between the two states for the whole step. No label records agreement or
disagreement; the verdict is derived, in this order:

| Test | Verdict | Effect on bits held |
|---|---|---|
| Shares nothing with what was admitted before (infinite surprise) | `conflicts` | Loss; the question is flagged |
| No earlier answer | `first_answer` | Gain against the declared space |
| Admits everything admitted before, or equals an existing answer | `repeats` | Zero surprise |
| After the step it cannot hold together with every other answer | `conflicts` | The question is flagged |
| Otherwise | `narrows` | Gain |

When the earlier state is consistent and one answer arrives, the gain equals the
surprise. Otherwise only the state difference is exact. An answer whose question's
space changed reads `space_changed`: cells of two spaces are never compared, and the
gain is taken from the two states. Each answer row says whether the claim's own
record changed or only its question did.

A question may be marked `focus`; gains are reported in total, on focus and off.
Read with the observation base, the two axes separate what a count cannot:

| Bits | Origin | Reading |
|---|---|---|
| Gain | New | New finding from new material |
| Gain | Held | New finding from material already held |
| Zero | New | The same finding from another source |
| Zero | Held | Restatement |
| Loss, infinite surprise | Either | Contradiction |
| None on focus | Either | Not about the questions in focus |

Commitment laws, each tested:

1. A repeated or weaker answer gains exactly zero, however it is worded.
2. One answer added to a consistent state, and consistent with it, gains exactly its
   surprise.
3. A contradiction has infinite surprise and lowers bits held. Two equally precise,
   disjoint answers cost exactly one bit.
4. Nothing is voted on. Two claims against one leave the question unresolved until a
   reviewed change settles it.
5. Bits held never exceed capacity. Digits finer than the step earn nothing. A
   declaration is bounded: 40 characters per number, 64 ranges per answer, 1,024
   values per space or answer.
6. The state depends on which answers are active, not on their order.
7. Step gains multiply, as exact ratios, to the final state.
8. A model that declares no questions measures zero and stays valid.

Equivalent claims that answer one question differently are reported, never
reconciled.

## Currency

Nothing here assigns a lifetime to a claim. How fast any one claim goes stale cannot
be known from its record, so the ledger measures only what the repository's own
history shows, and applies it to groups of claims, never to one.

**Clocks**, each exact for the revision measured:

- since the claim was admitted (first-parent committer time);
- since it was last reviewed in a completed maintenance record or explicitly
  reassessed in an admission closure, or never;
- since its newest evidence was reported, as a lower bound from source dates.

**Attrition.** A *loss of standing* is a reviewed change to the claim itself that
weakens it: its uncertainty is raised, a cited source is withdrawn along with its
origin, its own answer is widened or removed, or it leaves the active set. A change
to how a source is identified, or to a question, is not a loss. The ledger counts
losses against two exposures: claim-days, and claim reviews for the losses found in
the step that reviewed the claim. Each completed record counts a claim at most
once, including when a maintenance record both lists it as reviewed and reassesses
it. Each rate carries a 95% interval computed from the
two counts alone. Bits lost are counted the same way: a drop on a question whose
space changed, or that was retired, is not a loss. A committer time earlier than its
parent's is read as its parent's, so no span is negative. A loss that coincides with the claim being folded into an
equivalence group is counted apart, because there the repository reconciled grades
between duplicates and nothing was observed to change.

Loss is only found when a claim is reviewed. The claim-days no review has covered
are reported as `unseen`, so silence is never read as stability.

**Projection.** Expected losses over a horizon are stated for the whole model, with
an interval, and only for a horizon no longer than the recorded history.

**Walk-forward test.** For each day of history, the rate known at the start of the
day predicts a range for that day's losses, which is then compared with what
happened. The count of days inside the range is part of every report, so the
instrument re-tests itself as history grows.

## Automation

The validation workflow runs `information.py ci` as the last step of the integrity
job, using the trusted base-branch code on the proposed state. It appends a short
reading to the job summary and uploads the full reports as a seven-day artifact. The
step holds no secret or write token, changes no record, and cannot fail the job: it
continues on error, is time-limited, and the command itself always exits zero. The
reading is written part by part, so a history too long to replay within the time
allowed still leaves the ledger and the change on the page. A repository gets it
with the core update and needs to change nothing.

The ledger reads what the compiler reads: regular record files at their fixed
paths, parsed by the compiler's own strict loader, with each ID matching its file
name. A revision name is resolved to a commit ID before any other Git command sees
it.

```
python scripts/information.py --repo <world> ledger [--revision <rev>]
python scripts/information.py --repo <world> delta --before <rev> --after <rev>
python scripts/information.py --repo <world> replay [--revision <rev>]
python scripts/information.py --repo <world> ci [--before <rev>] [--out <dir>]
```

## Verification record

Replayed: a production world model at revision `ae44d37`, 66 first-parent revisions
over 11.6 days, 810 claims, 606 connectors, 914 evidence records, 4,394 source
records, 36 contributions and 29 completed maintenance records.

**The core change leaves real data untouched.** The whole state validates under the
changed compiler with identical record counts. Three of its real contributions,
re-admitted through the repository's own mechanical admission on the changed core,
reproduce the real commits record for record.

**Reading at that revision.** 810 claims, 753 propositions, 372 origins (367
observational, 4 generated, 1 testimonial), 1,201 links and 7,149 citations, of
which 5,948 repeat. Effective origins 106.9 (order 2) and 215.4 (Shannon). 604
claims rest on one origin; 66 have a reviewed independent origin. 605 of 606
connectors have no origin beyond their endpoints. 91 evidence and 353 source records
are inert.

**Replay.** All 66 steps balanced with no residual and the chain rule held.

**Verdicts checked against the records.** Four admissions scored `no_change` have
closures listing nothing created. One scored `unattached_material_only` added one
evidence record attached to no claim. Four scored `unmeasured_edit_only` rewrote 134
statements. Ten `reassessed` verdicts are uncertainty changes with unchanged support.
All 22 connector-only steps added connectors citing their endpoints' evidence.

**Known changes applied to the real state.** For every tenth claim: a repeat
citation, a new origin, a known origin newly bearing on the claim, a retirement and
an echo connector. Globally: rewording all statements, relabelling all records,
declaring a common parent for two origins, and laws 4 and 5 on 300 random pairs of
parts. Every reading matched the change exactly.

**Measured precision of origin identity.** The world keeps its own document
identifiers in free-form locators the ledger does not read. Against those:

| Identity available to the ledger | Origins | Steps differing | Largest step error |
|---|---|---|---|
| Address only (canonical fields today) | 372 (+7.8%) | 12 of 66 | 15 |
| Content digest declared | 357 (+3.5%) | 10 of 66 | 2 |
| World's own identifiers | 345 | 0 | 0 |

Every error in this sample is an over-count.

**Equivalence.** The repository's reviews had compared 197 pairs of claims: 57
equivalent, 100 overlapping, 40 distinct. They fold 57 claims into 45 groups, 20 of
which draw on more than one origin. The review cue raised 24 pairs during replay.
Reading all 24 found 22 restating the earlier claim. Review had since judged four of
them, all `equivalent`; 17 of the rest belong to the last admission, not yet
maintained. The cue found only 4 of the 57 pairs review judged equivalent, so it is
a narrow hint and the recorded judgments are the authority.

**Trend.** Across research admissions, by thirds, new origins per new claim fell
from 0.67 to 0.58 to 0.41 and known-origin share rose from 5% to 21% to 36%. The
last admission added 40 claims and 2 origins at 89% known-origin share.

**Support is not certainty.** The six low-uncertainty claims each rest on one origin;
they report proved theorems. The claims with the most origins are high-uncertainty
surveys reporting that many publications established nothing. A score multiplying
support into confidence would rank these backwards, which is why law 9 exists.

### Commitment, on an annotated slice

No record in the replayed model declares a question, so 29 questions and the answers
of 39 real claims were annotated by hand and overlaid on every revision. The
annotation is a reviewer's reading; the instrument did only arithmetic. The overlaid
records validated against the schemas and compiler checks at all 66 revisions, and
the model's 771 unannotated claims validated unchanged.

- **Repeats.** All 17 answers restating an earlier one gained exactly zero.
- **New from held material.** One step added four claims and no origin; it gained
  46.51 bits on four questions nothing had answered.
- **Restatement.** The last admission's 7 annotated claims gave 8 answers: 7 repeats
  and 1 first answer, for 1 bit.
- **Rewording.** Of 9 reworded answers, 5 lost nothing at the declared step and 4
  lost bits (three lost 3.46, one lost 1.00).
- **A real inconsistency.** One paper gives two dates for one event. Its claim
  admits both days and holds 7.52 of 8.52 bits: the inconsistency costs one bit.
- **Chain rule.** Step gains multiplied to the final ratio exactly over 66 steps.

Final state of the slice: 214.55 of 228.52 bits, 23 of 29 questions fully resolved.

**Calibration this replay forced.** A first version measured numeric answers by
interval width. Nine simulation outputs printed to 16 digits then held 470.73 bits
after one admission, against 10 for all ten focus questions. A score that rises with
printed digits is a vanity measure. Requiring a declared step fixed it: the same
admission reads 98.09 bits and no question can exceed its capacity.

**Contradiction was verified by injection only.** The model contains no pair of
claims admitted at different times that answer one question differently. Known
changes were injected into the real annotated state: a disjoint numeric answer
(infinite surprise, exactly −1 bit, +1 when withdrawn), one claim against two (1 bit
to 0), a narrowing and a partial overlap (gain equal to surprise), a weaker answer
(zero), 17 digits on a 0.01 grid (zero) and an off-focus answer (zero on focus).
Every reading matched.

### Currency

- **Clocks.** Median 7.6 days since admission and 7.2 days since last review; 40
  claims never reviewed. Newest evidence reported at least 325 days earlier at the
  median, and up to 28 years; 69 claims have no dated evidence.
- **Attrition.** 10 losses of standing in 5,618 claim-days: 0.0018 per claim-day
  (95% interval 0.0009 to 0.0033). Five were found in the step that reviewed the
  claim, among 1,483 claim reviews: 0.34% per review (0.14% to 0.79%). The other five
  fell on claims that step did not list as reviewed.
- **Cause that structure can see.** All 10 were uncertainty raised when the claim
  was folded into an equivalence group. Apart from folding, no loss was observed,
  which bounds that rate below 0.00065 per claim-day and shows no decay yet. Eleven
  days cannot show more.
- **Projection.** Over the next 7 days, 10.1 expected losses among 810 claims
  (4.8 to 18.6).
- **Walk-forward test.** 10 of 10 daily windows fell inside the predicted range. The
  ranges are wide at this length of history, so this is a weak test; it tightens as
  history accumulates.
- **Unseen.** 4,757 claim-days have passed since the claims' last reviews.

## Limits

- **Origin identity** depends on declared metadata. A shared address can still
  identify distinct works, and one work can appear at several addresses. Declaring
  `ancestry.content_sha256` or a common parent can identify copies of one work.
  Reviewed `independent` flags provide the ledger's evidence of independence.
- **A claim record is not a proposition** until review compares it. Uncompared
  restatements count as separate propositions.
- **Attribution is by claim**, not by proposition; folded claims keep their shares.
- **Commitment is measured only where declared.** Deciding that two claims answer
  one question, and what each admits, is a reviewed declaration the ledger cannot
  check. Levels depend on the declared space and step; verdicts do not. Sums across
  questions assume the questions are independent, so totals are upper bounds.
- **Currency sees only reviewed change.** It cannot tell a claim that held from one
  nobody re-examined, nor why a claim was weakened beyond what structure shows. With
  short history its intervals are wide, and no figure applies to a single claim.
- **Replay cost** grows with history length times model size. The automation step
  gives replay a time budget and reports the ledger and the change without it when
  the budget runs out. A long-lived repository will need incremental replay.

## Fields, and what is deferred

Commitment reads three optional fields added as canonical schema 1.3: question
`space` and `focus`, and claim `answers`. The compiler validates them, records
without them stay valid, and they enter a repository through reviewed maintenance.

Carrying the fields in contributions is implemented and was tested by re-admitting
three real contributions with them: each produced exactly the real admission plus
the declared fields. It is not part of this change. The public workflow service
lists the world submission protocols it supports, so declaring a new one needs a
coordinated service and plugin release.

Also deferred: scoring resolved `forecast` claims to learn what low, medium and high
mean empirically, the reviewed calibration `docs/Ontology.md` requires before any
probability is attached.

## Compatibility

Everything here is additive. `scripts/information.py` reads records and writes
reports. Schema 1.3 adds optional fields to the canonical claim and question schemas
and a compiler check (`scripts/answers.py`, fingerprinted with the other policy
files; compiler version 1.8.1, which bounds the size of a declaration). Existing records, old revisions and compiled packages
stay valid, and the compiled wrapper format stays 1.0 with native fields preserved.

The submission protocol, bundled submission schema, admission behavior, live
workflow references, public workflow service, host manifests and distribution bytes
are unchanged, so the installed plugin needs no release and no repository needs to
act. The scripts, schemas, workflow step, tests and documents are managed core files
and reach repositories through the ordinary core update.
