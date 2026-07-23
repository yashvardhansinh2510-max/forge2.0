// Privacy & Data policy copy — single source of truth.
// Rendered both in-app (app/(admin)/settings-privacy.tsx, behind staff auth)
// and on the public, unauthenticated /privacy route (app/privacy.tsx) that
// App Store Connect / Google Play Console require a hosted URL for. Keep
// both call sites importing this component rather than duplicating copy —
// the two are required to say the same thing.
//
// [LEGAL_ENTITY_NAME] / [REGISTERED_ADDRESS] / [CONTACT_EMAIL] /
// [EFFECTIVE_DATE] / [RETENTION_PERIOD] / [GRIEVANCE_OFFICER_NAME] /
// [GRIEVANCE_OFFICER_CONTACT] are placeholders — fill in with real business
// facts before this page is used for an App Store / Play Console
// submission or otherwise published.
import { View } from "react-native";

import { brand, space } from "@/src/design/tokens";
import { P, Section } from "@/src/components/LegalDocContent";

export function PrivacyPolicyContent() {
  return (
    <View style={{ gap: space.x6 }}>
      <Section title="What this covers">
        <P>
          {brand.name} is a workspace for staff to manage quotations, orders, and payments, and a
          portal customers use to view their own orders. This page describes what data the app
          collects, where it is stored, and how to exercise your rights over it.
        </P>
        <P>Effective date: [EFFECTIVE_DATE].</P>
      </Section>

      <Section title="Who operates this app">
        <P>
          {brand.name} is operated by [LEGAL_ENTITY_NAME], [REGISTERED_ADDRESS]. For any privacy
          question or request, contact [CONTACT_EMAIL].
        </P>
      </Section>

      <Section title="Data we collect">
        <P>Staff accounts: name, email, phone (optional), a hashed password, and role/floor
          assignment.</P>
        <P>Customer records (entered by staff, not by the customer): name, company, email, phone,
          address, city, and tax ID (GSTIN) where applicable. If customer portal access is enabled,
          the customer also gets a hashed password.</P>
        <P>Business records: quotations, purchase orders, payments, and an audit trail of changes
          made to them (who changed what, and when) — this is core to how the app functions and is
          retained as a business record, not discretionary tracking.</P>
      </Section>

      <Section title="Third-party processors">
        <P>Database records are hosted on MongoDB Atlas. Product photos, company logos, and
          document attachments are stored on Supabase. Both are third-party infrastructure
          providers processing data on our behalf, not independent data users.</P>
        <P>If enabled by your administrator, crash reports are sent to Sentry and product usage
          analytics to PostHog — both are off by default and only active if the relevant service
          credentials have been configured for this deployment.</P>
      </Section>

      <Section title="Data retention">
        <P>
          Staff and customer account records are retained for as long as the account is active.
          Quotations, purchase orders, and payment records are retained as business records for
          [RETENTION_PERIOD] after the underlying transaction completes, or as required by
          applicable tax/accounting law, whichever is longer — this applies even after the
          associated account is deactivated.
        </P>
      </Section>

      <Section title="Your rights">
        <P>
          You can request a copy of the personal data this app holds about you, ask that
          inaccurate data be corrected, or request deletion of your account (see "Requesting
          deletion" below). Some records may be retained after a deletion request where retention
          is required for financial record-keeping or to resolve an open business transaction.
        </P>
      </Section>

      <Section title="Requesting deletion">
        <P>
          Staff and customer accounts in this app are created by an administrator, not
          self-registered — to request that your account or personal data be deleted, contact the
          owner or manager who set up your access, or write to [CONTACT_EMAIL]. They can
          deactivate or remove the record; historical quotation/payment records tied to completed
          business transactions may be retained as required for financial record-keeping even
          after an account is deactivated.
        </P>
      </Section>

      <Section title="Grievance Officer">
        <P>
          If required in your jurisdiction: [GRIEVANCE_OFFICER_NAME] is the designated Grievance
          Officer for privacy-related complaints, reachable at [GRIEVANCE_OFFICER_CONTACT]. Remove
          this section if not applicable to where {brand.name} operates.
        </P>
      </Section>

      <Section title="Changes to this policy">
        <P>
          If this policy changes, the updated version will be posted at this same location with a
          new effective date above. Continued use of the app after a change takes effect means you
          accept the updated policy.
        </P>
      </Section>
    </View>
  );
}
