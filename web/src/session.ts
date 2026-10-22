// The current account.
//
// The app has no sign-in flow yet (see Settings: "Editing arrives with sign-in
// & the write backend"), so it runs read-only as the founder's seed account.
// CURRENT_HANDLE is the single stand-in every route reads for "who am I" —
// instead of the literal "nightdesk" copy-pasted across routes. When real auth
// lands, resolve it from the Supabase session here and no route changes.
export const CURRENT_HANDLE = "nightdesk";
