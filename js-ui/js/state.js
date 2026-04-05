// ============================================================
// STATE — singleton app state, avoids circular imports
// ============================================================

export const appState = {
  user:        null,   // Supabase user object
  userDetails: null,   // row from user_details table
};
