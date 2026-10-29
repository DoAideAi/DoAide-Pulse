// The API's length limits for the fields the editor types into, so an input
// stops where the schema would refuse the save. Autosave sends the whole piece
// in one PATCH: one field over its limit made every save a 422 — the body
// included — with the reason only in a hover tooltip. Kept equal to
// ContentUpdate by backend/tests/test_the_editor_limits_match_the_api.py.
export const TITLE_MAX = 300;
export const META_DESCRIPTION_MAX = 320;
export const EXCERPT_MAX = 1000;
