# Documentary renderer

A Remotion-based 1920x1080, 30fps documentary composition.

## Commands

- npm install
- npm run typecheck
- npm run studio
- npm run render:sample

The sample composition intentionally uses no external assets. Production manifests can supply local or HTTPS media sources, narration audio, music and frame-accurate captions.

Python timeline manifests are validated before conversion to renderer props. Footage scenes require source and license metadata; adjacent footage reuse is rejected.

Do not render unreviewed AI output as a factual documentary. The renderer is a presentation engine; source verification and editorial approval belong upstream.
