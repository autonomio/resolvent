# First real researcher smoke test

Repository unit tests exercise all routes, dry-run/admission, duplicate handling,
provenance and rejection cases using synthetic fixtures outside canonical directories.
They cannot establish that Claude selected a skill or that a user's connector has
been authorized. Perform this once in the authenticated researcher's Claude account:

1. Upload/enable the skill and enable the approved GitHub write connection.
2. Request a capability-only preflight for the chosen world-model repository.
3. In a real research chat, ask to capture one useful finding already present without
   new research. Verify that no new topic research was conducted, the provenance is
   marked retrospective and scope/coverage are accurate.
4. Verify the returned PR exists, contains only the contribution package, and reaches
   the existing admission/review agents. Verify admitted changes agree with evidence
   and that required checks/review prevent premature merge.
5. Repeat submission after a simulated transient failure with the same run ID; verify
   it does not duplicate the PR. Follow up with new material; verify a new linked run.

Do not merge synthetic smoke-test claims into the real empty model. Initial testing
should use the unit fixtures or a disposable PR that is closed without merge.
