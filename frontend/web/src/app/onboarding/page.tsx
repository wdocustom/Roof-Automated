"use client";

import { completeOnboarding } from "@/lib/api";
import { HardHat, Loader2, Phone, Building2, CheckCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
];

type Step = "company" | "provisioning" | "done";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("company");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Form fields
  const [companyName, setCompanyName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [zipCode, setZipCode] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [areaCode, setAreaCode] = useState("");

  // Result
  const [twilioNumber, setTwilioNumber] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    setStep("provisioning");

    try {
      const result = await completeOnboarding({
        company_name: companyName,
        phone: phone || undefined,
        email: email || undefined,
        address: address || undefined,
        city: city || undefined,
        state: state || undefined,
        zip_code: zipCode || undefined,
        contractor_license_number: licenseNumber || undefined,
        contractor_license_state: state || undefined,
        preferred_area_code: areaCode || undefined,
      });

      setTwilioNumber(result.twilio_phone_number);
      setStep("done");
    } catch {
      setError("Something went wrong. Please try again.");
      setStep("company");
    } finally {
      setLoading(false);
    }
  }

  if (step === "provisioning") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="text-center space-y-4">
          <Loader2 className="mx-auto h-12 w-12 text-orange-500 animate-spin" />
          <h2 className="text-xl font-semibold text-gray-900">
            Setting up your workspace...
          </h2>
          <p className="text-sm text-gray-500">
            Creating your company profile and provisioning a phone number.
            <br />
            This may take 10-15 seconds.
          </p>
        </div>
      </div>
    );
  }

  if (step === "done") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md text-center space-y-6">
          <CheckCircle className="mx-auto h-16 w-16 text-green-500" />
          <h2 className="text-2xl font-bold text-gray-900">You&apos;re all set!</h2>
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3 text-left">
            <div className="flex items-center gap-3">
              <Building2 className="h-5 w-5 text-gray-400" />
              <div>
                <p className="text-xs text-gray-500">Company</p>
                <p className="font-medium text-gray-900">{companyName}</p>
              </div>
            </div>
            {twilioNumber && (
              <div className="flex items-center gap-3">
                <Phone className="h-5 w-5 text-gray-400" />
                <div>
                  <p className="text-xs text-gray-500">Your SMS Number</p>
                  <p className="font-medium text-gray-900">{twilioNumber}</p>
                </div>
              </div>
            )}
            {!twilioNumber && (
              <p className="text-sm text-amber-600">
                Phone number provisioning is pending. You can add one later in Settings.
              </p>
            )}
          </div>
          <p className="text-sm text-gray-500">
            Customers can text {twilioNumber || "your number"} to get instant AI-powered
            quotes, scheduling, and updates.
          </p>
          <button
            onClick={() => router.push("/dashboard")}
            className="w-full rounded-lg bg-orange-600 px-4 py-3 text-sm font-medium text-white hover:bg-orange-700 transition-colors"
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-12">
      <div className="w-full max-w-lg space-y-8">
        <div className="text-center">
          <HardHat className="mx-auto h-12 w-12 text-orange-500" />
          <h1 className="mt-4 text-2xl font-bold text-gray-900">
            Set up your company
          </h1>
          <p className="mt-2 text-sm text-gray-500">
            We&apos;ll create your workspace and provision a dedicated phone number
            for AI-powered customer communication.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {error && (
            <p className="text-sm text-red-600 text-center bg-red-50 rounded-lg px-4 py-2">
              {error}
            </p>
          )}

          {/* Company Name */}
          <div>
            <label htmlFor="companyName" className="block text-sm font-medium text-gray-700">
              Company name <span className="text-red-500">*</span>
            </label>
            <input
              id="companyName"
              type="text"
              required
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
              placeholder="Smith Roofing & Siding"
            />
          </div>

          {/* Phone & Email */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="phone" className="block text-sm font-medium text-gray-700">
                Business phone
              </label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                placeholder="(555) 123-4567"
              />
            </div>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                Business email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                placeholder="info@smithroofing.com"
              />
            </div>
          </div>

          {/* Address */}
          <div>
            <label htmlFor="address" className="block text-sm font-medium text-gray-700">
              Business address
            </label>
            <input
              id="address"
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
              placeholder="123 Main St"
            />
          </div>

          {/* City / State / Zip */}
          <div className="grid grid-cols-6 gap-4">
            <div className="col-span-3">
              <label htmlFor="city" className="block text-sm font-medium text-gray-700">
                City
              </label>
              <input
                id="city"
                type="text"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                placeholder="Omaha"
              />
            </div>
            <div className="col-span-1">
              <label htmlFor="state" className="block text-sm font-medium text-gray-700">
                State
              </label>
              <select
                id="state"
                value={state}
                onChange={(e) => setState(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500 bg-white"
              >
                <option value="">--</option>
                {US_STATES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label htmlFor="zipCode" className="block text-sm font-medium text-gray-700">
                ZIP Code
              </label>
              <input
                id="zipCode"
                type="text"
                value={zipCode}
                onChange={(e) => setZipCode(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                placeholder="68102"
              />
            </div>
          </div>

          {/* Contractor License */}
          <div>
            <label htmlFor="license" className="block text-sm font-medium text-gray-700">
              Contractor license # <span className="text-xs text-gray-400">(optional)</span>
            </label>
            <input
              id="license"
              type="text"
              value={licenseNumber}
              onChange={(e) => setLicenseNumber(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
              placeholder="License number"
            />
          </div>

          {/* Preferred Area Code */}
          <div className="bg-orange-50 rounded-lg p-4 border border-orange-100">
            <label htmlFor="areaCode" className="block text-sm font-medium text-gray-700">
              Preferred area code for your AI phone number
              <span className="text-xs text-gray-400 ml-1">(optional)</span>
            </label>
            <p className="text-xs text-gray-500 mt-1 mb-2">
              We&apos;ll provision a local number customers can text for instant quotes.
              Pick an area code near your service area.
            </p>
            <input
              id="areaCode"
              type="text"
              maxLength={3}
              value={areaCode}
              onChange={(e) => setAreaCode(e.target.value.replace(/\D/g, ""))}
              className="block w-32 rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
              placeholder="402"
            />
          </div>

          <button
            type="submit"
            disabled={loading || !companyName}
            className="w-full rounded-lg bg-orange-600 px-4 py-3 text-sm font-semibold text-white hover:bg-orange-700 disabled:opacity-50 transition-colors"
          >
            Create Company & Get Phone Number
          </button>
        </form>
      </div>
    </div>
  );
}
