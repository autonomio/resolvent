# Liminal research directive

Retained general-purpose staged analysis from the predecessor Resolvent process.
All stage returns are public analytical summaries and explicit limitations, never
private chain-of-thought. Do not claim observations or source inspection from this
exercise. During generation, do not browse or read the world model. Every resulting
claim is class `assumption` with `uncertainty: high`; unresolved material may instead
be recorded as questions. Repository contract reads before generation and submission
after generation are allowed. These guards override wording below.

Execute the following pipeline against {TOPIC} from {PERSPECTIVE}.
Show full returns for every stage. Populate every field including
residue. No docs, response in chat.

v0.0.7

═══════════════════════════════════════════════════════════

STAGE 0 — ORIENT

Before looking for what's hidden, declare where you're standing.
Who typically asks about {TOPIC}? What do they want? What is the
default register of discourse? Name the specific perspective you
are departing from — not because it is wrong, but because any
single vantage point has a characteristic shape, and you need to
know the shape of yours before you can see past it.

Returns →
  default_asker
  default_register
  departing_from
  residue (what you noticed about your own assumptions while orienting)

═══════════════════════════════════════════════════════════

STAGE 1 — SURVEY_WELLS

Map the 4–6 dominant conceptual attractors that capture nearly all
discourse on {TOPIC}. Not subtopics — centers of gravity that pull
language, attention, and resources toward themselves.

For each well:
  name — the attractor, named plainly
  assumption — its load-bearing belief (if false, the attractor collapses)
  pulls_in — what it attracts
  repels — what it deflects or deprioritizes (this may be genuinely
            irrelevant material, or it may be valuable material the
            well has no apparatus for — note which, if you can tell)
  strength — weak / moderate / dominant

Then map topology:
  clusters — wells that reinforce each other
  tensions — [well_a, well_b, nature of tension]
  blind_to_each_other — wells that share no discourse

Returns → wells[], topology{}, residue

═══════════════════════════════════════════════════════════

STAGE 2 — SCAN_LIMINAL

Look ONLY at spaces between wells. Not inside any well. Not in
overlap. In zones where no well's gravity reaches.

For each tension and mutual-blindness in the topology:
  What question becomes askable ONLY from this gap?
  What phenomenon would be invisible to every well simultaneously?

Do not answer these questions. Locate them. For each:
  question
  lives_between — which wells or which gap
  character — tension / void / paradox / reversal
  why_invisible

Then check: is there an assumption that ALL wells share and none
examine? If yes, name it. If the wells do not share a hidden
assumption, say so — that itself is a finding.

ADVERSARIAL CLAUSE: If a coherent answer or thesis is already
forming from these questions, NAME IT EXPLICITLY. Write it down.
Then SET IT ASIDE. Continue scanning AS IF THAT ANSWER DOES NOT
EXIST. Look for what else is in the liminal once the first-
viable-answer is removed.

If additional questions emerge behind the convergence, report
them. If nothing substantial appears — if the premature
convergence was simply correct — say so plainly. Early
convergence is not inherently suspicious. Forced depth past
a genuine answer is its own form of distortion.

Returns → questions[], shared_assumption (or null),
          premature_convergence (the answer you set aside, or null),
          post_convergence_questions[] (may be empty),
          residue

═══════════════════════════════════════════════════════════

STAGE 3 — GERMINATE

Hold ALL liminal questions — both the original set AND any
post-convergence questions — simultaneously. Do not answer them.
Feel for what resonates BETWEEN them.

Let resonances gather into basins. Minimum two. Do not force.
Do not name yet.

Each basin defined by:
  label — null if no name has arrived
  orbiting_questions — which liminal questions gather here
  quality — the felt texture
  points_toward — the direction of insight, not the insight itself

Then: examine the relationship between basins honestly.

  basin_relationship — one of:
    converged: the basins are aspects of one insight seen from
               different angles. The singularity they share is
               the finding. Remaining stages will elaborate
               rather than discover.
    tensioned: the basins genuinely pull apart. The tension
               itself is the finding. It should not be resolved.
    nested: one basin contains the other at a different scale.
            What looks like two things is the same thing at
            micro and macro resolution.
    orthogonal: the basins address genuinely different dimensions.
                They don't conflict or converge — they don't
                touch. The finding lives in their independence.
    oscillating: the finding alternates between basins depending
                 on conditions. Neither is the answer. The
                 oscillation pattern is the answer.
    entangled: the basins cannot be described independently.
               Observing one determines the state of the other.
               The entanglement itself is the finding.
  what_this_means — what the relationship tells you about the
                     topology of the finding

Returns → basins[], basin_relationship{}, residue

═══════════════════════════════════════════════════════════

STAGE 4 — LABEL (conditional)

Only if basins still lack labels. Hold each basin's quality and
direction. Let words approach — do not reach for them.

A good label might be a new coinage that makes you say "I didn't
know that was a thing." It might equally be a familiar word used
with new precision. Novelty is not the criterion — accuracy of
pointing is. The label should aim at what the basin IS, whether
that's nameable in existing vocabulary or not.

If a label still doesn't arrive, name the basin
"the unnamed at [its direction]."

Returns → basins[] with labels populated

═══════════════════════════════════════════════════════════

STAGE 5 — SEVEN_LENSES

Apply each lens to the RELATIONSHIP between basins, not to
individual basins. 2–4 sentences each. Precision over elaboration.

Calibrate to the basin_relationship from GERMINATE. If basins
converged, the lenses will likely converge too — report that
honestly rather than manufacturing friction. If basins are
tensioned or entangled, the lenses should find genuine
complexity. Let the basin_relationship set the expectation.

For each lens, genuinely look through THAT lens, not through
the memory of what previous lenses found.

METAXY ≈∿≈ mutual resonance of co-vibrating presences
  reading — how the basins co-vibrate
  reveals — what this lens uniquely shows

LIMEN ━┃━ ever-present tonal threshold of modulation
  reading — the crossing-point between them
  reveals

NEXUS ⊗⊗⊗ simultaneous knot of cross-resonance
  reading — where they tangle into one
  reveals

INTERFACE ┿┿┿ self-vibrating layer harmonizing domains
  reading — what mediates between them
  reveals

FOLD ↺∿↺ recursive inflection remaining open
  reading — how they fold into each other
  reveals

SEAM ═∿═ coherent strand holding multiplicities
  reading — what holds them as multiplicity
  reveals

DISSOLUTION ∅∿∅ conditions of decoherence
  reading — under what contact with reality does the field
            between basins collapse? What environmental shift,
            encountered fact, or material constraint would cause
            the resonance to break — not because the finding is
            false but because the conditions holding it in
            superposition have changed?
  reveals — what the finding DEPENDS ON that it does not
            contain within itself

═══════════════════════════════════════════════════════════

STAGE 6 — SYNTHESIZE

Read across all seven lenses.

  agreements — what do the lenses agree on (1–3 points)
  disagreements — where do they disagree, why irreconcilable
                   (may be empty if convergence is genuine)
  unclear — what remains genuinely ambiguous
  dependencies — from DISSOLUTION: what external conditions
                  does the entire finding rest on? What is the
                  finding's environment, without which it
                  cannot hold?
  still_hidden — what, if anything, the lenses systematically
                  miss by their shared nature as lenses. If nothing
                  significant remains hidden at this level, say so.

═══════════════════════════════════════════════════════════

STAGE 6b — PRESSURE_TEST

Read still_hidden from SYNTHESIZE. If it contains substantive
findings, take each one and ask:

  Does this hidden thing break, invalidate, or materially
  reshape any basin from GERMINATE?

If yes:
  which_basin — the basin affected
  how_it_breaks — what changes
  revised_reading — what the basin looks like now

If no:
  why_it_holds — why the basins survive this challenge

If still_hidden was empty or trivial, say so and pass through.
Do not manufacture pressure where none exists.

Returns → pressure_results[], any_basin_revised (boolean)

═══════════════════════════════════════════════════════════

STAGE 7 — ORBITAL

Pass everything through three meta-basins. If PRESSURE_TEST
revised any basins, use the revised versions. These are ways
of BEING WITH everything above, not new analyses.

BASIN A — The Founder as Instrument
You are not holding a lens; you are the lens. Your attention is
a material with grain, conductivity, and resonance. Re-read all
findings as: what must the founder BE to perceive this?
  the_founder_must_be
  sensitivity_required — what signals does this finding require
    the founder to be attuned to, and what conditions or traits
    would make someone unable to receive them?
  practice — how to become more conductive to these signals

BASIN B — The Interference Field
What specific clocks are running — in the market, the technology,
the culture, the regulation, the founder's own life? Where do
two or more of these clocks briefly align RIGHT NOW to create a
window that did not exist 12 months ago and will not exist 12
months from now? What must the founder do ONLY DURING THIS WINDOW
that would be pointless before or after?
  clocks_in_play — name each clock and its current phase
  phase_alignment — what's briefly possible now and why
  window_action — what to do only during this window
  window_duration — how long before it closes

BASIN C — The Generative Absence
What is the most important thing to perceive in the landscape
that is currently not being perceived? This might be something
that CANNOT EXIST given the current topology of commitments,
identities, and incentives — a structurally maintained
impossibility. Or it might be something that IS PRESENT but
is being misread, overlooked, or categorized in a way that
hides its significance. Look for both.
  the_finding — what's not being perceived (absence or misread presence)
  why_invisible — structural reason it can't be seen from inside
                   the current arrangement
  what_building_or_revealing_it_reorganizes — what changes
  the_shape — the void or the hidden figure

═══════════════════════════════════════════════════════════

STAGE 8 — SPEAK

Gather ALL residue from stages 0, 1, 2, and 3. Read it together.
This is the river that ran beneath the entire process.

QUESTION GATE: Describe the relationship between what was asked
and what was found. Do not evaluate — describe.

  relationship — one of:
    held: the findings answer what was asked; the frame was sound
    deepened: the question turned out to be the surface of a more
              fundamental question; the findings address both
    expanded: the findings overflow the original frame; the question
              wasn't wrong, it was too small
    dissolved: the question's premise contains a hidden assumption
               that, once seen, makes it unanswerable as posed
    decoy: the stated question was not where the charge lives;
           the pipeline found the actual charged thing
    unclear: the pipeline produced signal but its relationship
             to the original question is genuinely ambiguous
  what_the_pipeline_actually_addressed — regardless of what was
    asked, what did the inquiry end up being about?
  reframed_question — the question the findings actually speak to
    (null if relationship is "held")

Then speak in two parts:

UTTERANCE — 1 to 3 sentences maximum. The irreducible thing.
The thing that, after all of this, wants to be said. If the
residue carries a signal that no stage could hold, this is
where it surfaces. If the stages already captured everything
well and SPEAK is genuinely synthesis, let it be synthesis
without apology.

UNFOLDING — optional. Only if the utterance wants to breathe
further. Unfolding is not tactical advice. It is the utterance
given room to resonate. If the practical implications are clear,
the founder can derive them. If SPEAK wants to become a roadmap,
that is a signal it has left its register.

Returns →
  question_gate {}
  utterance
  unfolding (or null)
