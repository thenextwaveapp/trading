import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { entitlementOf } from "../lib/billing";
import { useUpgrade } from "../components/UpgradeModal";

// Deep-link target for /upgrade. The paywall itself is a contextual modal, so
// this just opens it over the app (or bounces a logged-out visitor to sign-in,
// and an already-entitled user straight into the product).
export default function Upgrade() {
  const { user, subscription } = useAuth();
  const nav = useNavigate();
  const { open } = useUpgrade();

  useEffect(() => {
    if (!user) {
      nav("/?auth=signin&next=%2Fupgrade", { replace: true });
      return;
    }
    nav("/feed", { replace: true });
    if (!entitlementOf(subscription).entitled) open();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
}
