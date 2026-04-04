"use client";

import { useState, useEffect } from "react";
import { CheckCircle, AlertCircle, FileText, Clock, Shield } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface ContractData {
  contract_id: string;
  token: string;
  status: string;
  html_content: string;
  contract_amount: number;
  payment_schedule: { milestone: string; percentage: number; amount: number }[];
  company_name: string;
  company_phone: string | null;
  company_license: string | null;
  signed_at: string | null;
  signer_name: string | null;
  is_expired: boolean;
  expires_at: string | null;
}

export default function ContractSigningPage({ params }: { params: { token: string } }) {
  const { token } = params;
  const [contract, setContract] = useState<ContractData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [signerName, setSignerName] = useState("");
  const [signing, setSigning] = useState(false);
  const [signed, setSigned] = useState(false);
  const [agreed, setAgreed] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/public/contracts/${token}`)
      .then((r) => {
        if (!r.ok) throw new Error("Contract not found");
        return r.json();
      })
      .then((data) => {
        setContract(data);
        if (data.status === "signed") {
          setSigned(true);
          setSignerName(data.signer_name || "");
        }
      })
      .catch(() => setError("Contract not found or link is invalid."))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSign() {
    if (!signerName.trim() || !agreed) return;
    setSigning(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/public/contracts/${token}/sign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signer_name: signerName.trim() }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Signing failed");
      }
      setSigned(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Signing failed. Please try again.");
    } finally {
      setSigning(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="animate-pulse text-center">
          <FileText className="h-12 w-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-400">Loading contract...</p>
        </div>
      </div>
    );
  }

  if (error && !contract) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="text-center max-w-sm">
          <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-3" />
          <h1 className="text-lg font-semibold text-gray-900 mb-2">Oops</h1>
          <p className="text-gray-600 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  if (!contract) return null;

  // Signed state
  if (signed) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-green-50 to-white">
        <div className="max-w-lg mx-auto px-4 py-12 text-center">
          <div className="bg-white rounded-2xl shadow-lg p-8">
            <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-gray-900 mb-2">Contract Signed!</h1>
            <p className="text-gray-600 mb-6">
              Thank you, {contract.signer_name || signerName}. Your contract with{" "}
              <strong>{contract.company_name}</strong> is confirmed.
            </p>
            <div className="bg-green-50 rounded-xl p-4 text-left space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Contract Amount</span>
                <span className="font-semibold text-gray-900">
                  ${contract.contract_amount.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </span>
              </div>
              {contract.signed_at && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Signed</span>
                  <span className="text-gray-900">{new Date(contract.signed_at).toLocaleString()}</span>
                </div>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-6">
              A confirmation has been sent to your phone. Questions? Text{" "}
              {contract.company_phone || "your contractor"}.
            </p>
          </div>
          <div className="mt-4 flex items-center justify-center gap-1 text-xs text-gray-400">
            <Shield className="h-3 w-3" /> Secured by Roof Automated
          </div>
        </div>
      </div>
    );
  }

  // Expired state
  if (contract.is_expired) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="text-center max-w-sm">
          <Clock className="h-12 w-12 text-amber-400 mx-auto mb-3" />
          <h1 className="text-lg font-semibold text-gray-900 mb-2">Contract Expired</h1>
          <p className="text-gray-600 text-sm">
            This contract expired on{" "}
            {contract.expires_at ? new Date(contract.expires_at).toLocaleDateString() : "recently"}.
            Contact {contract.company_name} to request a new one.
          </p>
          {contract.company_phone && (
            <a
              href={`sms:${contract.company_phone}`}
              className="mt-4 inline-block bg-orange-600 text-white px-6 py-2 rounded-lg text-sm font-medium"
            >
              Text {contract.company_name}
            </a>
          )}
        </div>
      </div>
    );
  }

  // Main signing view
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-lg mx-auto px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wider">Contract from</p>
            <p className="font-semibold text-gray-900">{contract.company_name}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-400">Total</p>
            <p className="text-lg font-bold text-gray-900">
              ${contract.contract_amount.toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </p>
          </div>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-6">
        {/* Contract content */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
            <FileText className="h-5 w-5 text-gray-400" />
            <h2 className="font-semibold text-gray-900">Contract Details</h2>
          </div>
          <div
            className="px-5 py-4 prose prose-sm max-w-none
              [&_h2]:text-lg [&_h2]:font-bold [&_h2]:mb-3 [&_h2]:text-gray-900
              [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:uppercase [&_h3]:tracking-wider [&_h3]:text-gray-500 [&_h3]:mt-6 [&_h3]:mb-2
              [&_p]:text-sm [&_p]:text-gray-700 [&_p]:leading-relaxed [&_p]:mb-2
              [&_ol]:text-sm [&_ol]:text-gray-700 [&_ol]:space-y-2
              [&_li]:leading-relaxed
              [&_table]:w-full [&_table]:text-sm [&_table]:border-collapse
              [&_th]:text-left [&_th]:text-gray-500 [&_th]:font-medium [&_th]:py-2 [&_th]:border-b [&_th]:border-gray-200
              [&_td]:py-2 [&_td]:border-b [&_td]:border-gray-100 [&_td]:text-gray-900
              [&_strong]:text-gray-900"
            dangerouslySetInnerHTML={{ __html: contract.html_content }}
          />
        </div>

        {/* Payment Schedule summary */}
        {contract.payment_schedule.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-3">
              Payment Summary
            </h3>
            <div className="space-y-3">
              {contract.payment_schedule.map((item, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{item.milestone}</p>
                    <p className="text-xs text-gray-400">{item.percentage}% of total</p>
                  </div>
                  <p className="text-sm font-semibold text-gray-900">
                    ${item.amount.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </p>
                </div>
              ))}
              <div className="border-t border-gray-200 pt-3 flex items-center justify-between">
                <p className="text-sm font-semibold text-gray-900">Total</p>
                <p className="text-base font-bold text-gray-900">
                  ${contract.contract_amount.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Signing section */}
        <div className="bg-white rounded-xl shadow-sm border-2 border-orange-200 p-5 space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500">
            Sign Contract
          </h3>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Your Full Legal Name
            </label>
            <input
              type="text"
              value={signerName}
              onChange={(e) => setSignerName(e.target.value)}
              placeholder="e.g. John Smith"
              className="w-full rounded-lg border border-gray-300 px-4 py-3 text-base
                focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none"
              autoComplete="name"
            />
          </div>

          {signerName.trim() && (
            <div className="bg-gray-50 rounded-lg p-4 text-center">
              <p className="text-xs text-gray-400 mb-1">Your signature</p>
              <p className="text-2xl font-serif italic text-gray-900">{signerName}</p>
            </div>
          )}

          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 h-5 w-5 rounded border-gray-300 text-orange-600
                focus:ring-orange-500"
            />
            <span className="text-xs text-gray-600 leading-relaxed">
              I have read and agree to the terms of this contract. I understand that
              typing my name and clicking &quot;Sign Contract&quot; constitutes a
              legally binding electronic signature under the ESIGN Act.
            </span>
          </label>

          <button
            onClick={handleSign}
            disabled={!signerName.trim() || !agreed || signing}
            className="w-full bg-orange-600 text-white py-4 rounded-xl text-base font-semibold
              hover:bg-orange-700 disabled:opacity-40 disabled:cursor-not-allowed
              transition-colors active:scale-[0.98]"
          >
            {signing ? "Signing..." : "Sign Contract"}
          </button>
        </div>

        {/* Footer */}
        <div className="text-center pb-8">
          <div className="flex items-center justify-center gap-1 text-xs text-gray-400 mb-2">
            <Shield className="h-3 w-3" /> Secured by Roof Automated
          </div>
          <p className="text-xs text-gray-400">
            Questions? Text {contract.company_phone || "your contractor"} or reply to the original message.
          </p>
        </div>
      </div>
    </div>
  );
}
