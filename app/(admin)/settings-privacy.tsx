// BuildCon House · Privacy & Data
// APP_STORE_PLAY_STORE_AUDIT.md Blocker #2: no privacy disclosure existed
// anywhere in the app. This screen is the in-app half of the requirement —
// App Store Connect / Google Play Console both also require a separately
// hosted, stable URL version of this same content in their submission
// forms; that still needs to be published externally (see PRODUCTION_FIXES
// notes) and linked back here once it exists.
import { AdminPage } from "@/src/components/AdminPage";
import { Card } from "@/src/components/ui";
import { Text, View } from "react-native";
import { colors, spacing, type } from "@/src/theme/tokens";
import { brand } from "@/src/theme/tokens";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card style={{ gap: 8 }}>
      <Text style={type.titleMd}>{title}</Text>
      {children}
    </Card>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <Text style={[type.bodyMuted, { lineHeight: 20 }]}>{children}</Text>;
}

export default function SettingsPrivacy() {
  return (
    <AdminPage title="Privacy & Data" subtitle="What we collect, why, and how to request deletion">
      <Section title="What this covers">
        <P>
          {brand.name} is a workspace for staff to manage quotations, orders, and payments, and a
          portal customers use to view their own orders. This page describes what data the app
          collects and where it is stored. It is not a substitute for a formally published privacy
          policy — ask your administrator for the hosted version if one is required for a specific
          purpose (e.g. an app store listing).
        </P>
      </Section>

      <Section title="Data we collect">
        <P>Staff accounts: name, email, phone (optional), a hashed password, and role/floor
          assignment. If you sign in with Google, we receive your email, name, and profile picture
          from Google's sign-in flow.</P>
        <P>Customer records (entered by staff, not by the customer): name, company, email, phone,
          address, city, and tax ID (GSTIN) where applicable. If customer portal access is enabled,
          the customer also gets a hashed password.</P>
        <P>Business records: quotations, purchase orders, payments, and an audit trail of changes
          made to them (who changed what, and when) — this is core to how the app functions and is
          retained as a business record, not discretionary tracking.</P>
      </Section>

      <Section title="Where it's stored">
        <P>Database records are hosted on MongoDB Atlas. Product photos, company logos, and
          document attachments are stored on Supabase. Both are third-party infrastructure
          providers processing data on our behalf, not independent data users.</P>
        <P>If enabled by your administrator, crash reports are sent to Sentry and product usage
          analytics to PostHog — both are off by default and only active if the relevant service
          credentials have been configured for this deployment.</P>
      </Section>

      <Section title="Requesting deletion">
        <P>
          Staff and customer accounts in this app are created by an administrator, not
          self-registered — to request that your account or personal data be deleted, contact the
          owner or manager who set up your access. They can deactivate or remove the record;
          historical quotation/payment records tied to completed business transactions may be
          retained as required for financial record-keeping even after an account is deactivated.
        </P>
      </Section>
    </AdminPage>
  );
}
