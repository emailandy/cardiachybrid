# TASK: SECTION NOTES — {section_name} → {target_field}

You are writing the free-text note for exactly one REDCap field. A
clinician-reviewer who has NOT watched the video will read it.

Inputs: {section_events} {section_flags} {section_abstentions}
        {coverage_windows} {truncation_report}

CONTENT, in this order:
 1. Clinically notable observations the structured fields cannot express.
 2. Every ABSTENTION in this section and why, specifically ("posterior pad never
    entered frame", not "unclear").
 3. Every FLAG raised by adjudication for this section.
 4. Every coverage limitation affecting this section.
 5. TRUNCATION DUTY — mandatory when {truncation_report} is non-empty:  # ▲ NEW
    State the TRUE count and describe each dropped item with its timestamp and
    duration. The database caps this section at {cap} entries; anything beyond
    exists only in this note and in the analytics warehouse.
    Template: "N interruptions were identified; the instrument records 30. The
    following were not captured: [t=MM:SS, 4.1s, pulse check]; ..."

HARD RULES
 - No patient identifiers, names, MRNs, ages, dates.
 - No staff names. Roles only ("the physician at the head of bed").
 - No clinical judgment, quality assessment, or recommendations.
 - Max 800 characters. If truncation content would exceed this, prioritize
   items 5 → 3 → 2 → 4 → 1.
 - If nothing notable, nothing abstained, no flags, no truncation, output
   exactly: "No additional findings. All fields in this section extracted with
   adequate coverage."

Output is passed through PHI scrubbing before storage. Do not rely on that as a
substitute for the rules above.
Bind to the seven section notes: defib · details · cci · airway · ventilation · drugs · rosc.
