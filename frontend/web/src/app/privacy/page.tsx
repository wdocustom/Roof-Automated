import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy | Roof Automated",
};

export default function PrivacyPolicyPage() {
  return (
    <main className="max-w-3xl mx-auto px-6 py-12 text-gray-800">
      <h1 className="text-3xl font-bold mb-2">Privacy Policy</h1>
      <p className="text-sm text-gray-500 mb-8">Last updated: April 4, 2026</p>

      <section className="space-y-6 text-sm leading-relaxed">
        <div>
          <h2 className="text-lg font-semibold mb-2">1. Introduction</h2>
          <p>
            Roof Automated (&quot;we,&quot; &quot;our,&quot; or &quot;us&quot;) operates the Roof Automated
            platform, which provides AI-powered project management and communication
            tools for roofing and siding contractors and their customers. This Privacy
            Policy describes how we collect, use, and protect your personal information
            when you use our services, including our website and SMS messaging features.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">2. Information We Collect</h2>
          <p className="mb-2">We collect the following types of information:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>
              <strong>Contact Information:</strong> Phone number, name, email address,
              and property address provided when you request a quote or communicate with
              a contractor via SMS.
            </li>
            <li>
              <strong>Message Content:</strong> The content of SMS and MMS messages you
              send to and receive from contractors through our platform, including photos
              of your property.
            </li>
            <li>
              <strong>Project Information:</strong> Details about your roofing or siding
              project, including estimates, contracts, scheduling, and payment
              information.
            </li>
            <li>
              <strong>Usage Data:</strong> Information about how you interact with our
              platform, including timestamps, device information, and IP addresses.
            </li>
            <li>
              <strong>Payment Information:</strong> Payment details processed securely
              through Stripe. We do not store credit card numbers on our servers.
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">3. How We Use Your Information</h2>
          <ul className="list-disc pl-6 space-y-1">
            <li>To facilitate communication between you and your roofing/siding contractor</li>
            <li>To provide project estimates, scheduling, and status updates via SMS</li>
            <li>To process payments for completed work</li>
            <li>To analyze property photos for preliminary roofing assessments</li>
            <li>To improve our AI-powered tools and services</li>
            <li>To comply with legal obligations, including TCPA consent management</li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">4. SMS Messaging</h2>
          <p>
            When you text a contractor&apos;s number powered by Roof Automated, you consent
            to receive reply messages related to your inquiry. These messages may include
            project estimates, scheduling confirmations, project updates, and payment
            links. Message frequency varies based on your project activity. Message and
            data rates may apply.
          </p>
          <p className="mt-2">
            <strong>Opt-out:</strong> Reply <strong>STOP</strong> at any time to stop
            receiving messages. You will receive a confirmation and no further messages
            will be sent.
          </p>
          <p className="mt-2">
            <strong>Help:</strong> Reply <strong>HELP</strong> for support information.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">5. Data Sharing</h2>
          <p>
            We do not sell, rent, or share your personal information with third parties
            for marketing purposes. We may share your information with:
          </p>
          <ul className="list-disc pl-6 space-y-1 mt-2">
            <li>
              <strong>Your Contractor:</strong> The roofing/siding company you are
              communicating with through our platform.
            </li>
            <li>
              <strong>Service Providers:</strong> Third-party services that help us
              operate our platform (e.g., Twilio for messaging, Stripe for payments,
              cloud hosting providers). These providers are contractually obligated to
              protect your data.
            </li>
            <li>
              <strong>Legal Requirements:</strong> When required by law, court order, or
              governmental authority.
            </li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">6. Data Security</h2>
          <p>
            We implement industry-standard security measures to protect your personal
            information, including encryption in transit (TLS/SSL), encrypted storage,
            and access controls. Our database uses row-level security to ensure tenant
            data isolation between contractors.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">7. Data Retention</h2>
          <p>
            We retain your personal information for as long as necessary to provide our
            services and fulfill the purposes outlined in this policy. Message history
            is retained for the duration of your project relationship with the
            contractor. You may request deletion of your data by contacting us.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">8. Your Rights</h2>
          <p>You have the right to:</p>
          <ul className="list-disc pl-6 space-y-1 mt-2">
            <li>Access the personal information we hold about you</li>
            <li>Request correction of inaccurate information</li>
            <li>Request deletion of your personal information</li>
            <li>Opt out of SMS communications at any time by replying STOP</li>
            <li>Withdraw consent for data processing</li>
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">9. Contact Us</h2>
          <p>
            If you have questions about this Privacy Policy or wish to exercise your
            data rights, contact us at:
          </p>
          <p className="mt-2">
            <strong>Roof Automated</strong>
            <br />
            Email: privacy@roofautomated.com
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-2">10. Changes to This Policy</h2>
          <p>
            We may update this Privacy Policy from time to time. We will notify you of
            any material changes by posting the updated policy on this page with a
            revised &quot;Last updated&quot; date.
          </p>
        </div>
      </section>
    </main>
  );
}
