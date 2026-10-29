// The API's length limits for the fields the editor types into, so an input
// stops where the schema would refuse the save. Autosave sends the whole piece
// in one PATCH: one field over its limit made every save a 422 — the body
// included — with the reason only in a hover tooltip. Kept equal to
// ContentUpdate by backend/tests/test_the_editor_limits_match_the_api.py.
export const TITLE_MAX = 300;
export const META_DESCRIPTION_MAX = 320;
export const EXCERPT_MAX = 1000;

// A *new* password's bounds: UserCreate and PasswordResetConfirm. Only ever on
// a field that sets one — sign-in checks what an existing password is, and an
// account made before a rule changed (or seeded with a short SEED_PASSWORD) was
// refused by the browser before the server was asked. Kept equal to the API by
// the same test.
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;
