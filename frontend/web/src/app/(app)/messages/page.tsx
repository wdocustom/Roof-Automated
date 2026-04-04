"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useRef, useEffect } from "react";
import { formatDistanceToNow } from "date-fns";
import {
  MessageSquare,
  Send,
  User,
  Bot,
  ArrowLeft,
  Plus,
  Loader2,
} from "lucide-react";
import { clsx } from "clsx";
import {
  fetchConversations,
  fetchThread,
  sendMessage,
  type Conversation,
} from "@/lib/api";

export default function MessagesPage() {
  const queryClient = useQueryClient();
  const [selectedPhone, setSelectedPhone] = useState<string | null>(null);
  const [composeText, setComposeText] = useState("");
  const [showNewConvo, setShowNewConvo] = useState(false);
  const [newPhone, setNewPhone] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const conversations = useQuery({
    queryKey: ["conversations"],
    queryFn: fetchConversations,
  });

  const thread = useQuery({
    queryKey: ["thread", selectedPhone],
    queryFn: () => fetchThread(selectedPhone!),
    enabled: !!selectedPhone,
  });

  const sendMutation = useMutation({
    mutationFn: sendMessage,
    onSuccess: () => {
      setComposeText("");
      queryClient.invalidateQueries({ queryKey: ["thread", selectedPhone] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  // Scroll to bottom when thread updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread.data?.messages]);

  function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!composeText.trim() || !selectedPhone) return;
    sendMutation.mutate({
      to_phone: selectedPhone,
      body: composeText.trim(),
    });
  }

  function startNewConversation() {
    if (!newPhone.trim()) return;
    // Normalize phone: ensure +1 prefix for US numbers
    let phone = newPhone.replace(/[\s()-]/g, "");
    if (!phone.startsWith("+")) {
      phone = phone.startsWith("1") ? `+${phone}` : `+1${phone}`;
    }
    setSelectedPhone(phone);
    setShowNewConvo(false);
    setNewPhone("");
  }

  return (
    <div className="flex h-[calc(100vh-57px)] overflow-hidden">
      {/* Conversation list */}
      <div
        className={clsx(
          "w-full md:w-80 border-r border-gray-200 bg-white flex flex-col",
          selectedPhone ? "hidden md:flex" : "flex"
        )}
      >
        <div className="px-6 py-5 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Messages</h1>
            <p className="text-sm text-gray-500 mt-1">SMS conversations</p>
          </div>
          <button
            onClick={() => setShowNewConvo(true)}
            className="h-8 w-8 rounded-lg bg-orange-100 flex items-center justify-center text-orange-600 hover:bg-orange-200 transition-colors"
            title="New conversation"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>

        {/* New conversation input */}
        {showNewConvo && (
          <div className="px-4 py-3 border-b border-gray-200 bg-orange-50">
            <p className="text-xs font-medium text-gray-600 mb-2">
              New conversation
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                startNewConversation();
              }}
              className="flex gap-2"
            >
              <input
                type="tel"
                value={newPhone}
                onChange={(e) => setNewPhone(e.target.value)}
                placeholder="+1 (555) 123-4567"
                className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                autoFocus
              />
              <button
                type="submit"
                className="px-3 py-1.5 rounded-lg bg-orange-600 text-white text-sm font-medium hover:bg-orange-700"
              >
                Go
              </button>
            </form>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {conversations.isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="h-16 bg-gray-100 animate-pulse rounded-lg"
                />
              ))}
            </div>
          ) : !conversations.data?.length ? (
            <div className="flex flex-col items-center justify-center py-16 text-gray-400">
              <MessageSquare className="h-10 w-10 mb-3" />
              <p className="text-sm">No conversations yet</p>
              <button
                onClick={() => setShowNewConvo(true)}
                className="mt-2 text-xs text-orange-600 hover:text-orange-700 font-medium"
              >
                Start a new conversation
              </button>
            </div>
          ) : (
            conversations.data.map((conv) => (
              <button
                key={conv.phone_number}
                onClick={() => setSelectedPhone(conv.phone_number)}
                className={clsx(
                  "w-full px-4 py-3 text-left border-b border-gray-100 hover:bg-gray-50 transition-colors",
                  selectedPhone === conv.phone_number && "bg-orange-50"
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-900">
                    {conv.phone_number}
                  </span>
                  {conv.last_message_at && (
                    <span className="text-xs text-gray-400">
                      {formatDistanceToNow(new Date(conv.last_message_at), {
                        addSuffix: true,
                      })}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-1 truncate">
                  {conv.last_message || "No messages"}
                </p>
                <span className="text-xs text-gray-400">
                  {conv.message_count} message
                  {conv.message_count !== 1 ? "s" : ""}
                </span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Message thread */}
      <div
        className={clsx(
          "flex-1 flex flex-col bg-gray-50",
          !selectedPhone ? "hidden md:flex" : "flex"
        )}
      >
        {!selectedPhone ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <MessageSquare className="h-12 w-12 mx-auto mb-3" />
              <p className="text-sm">Select a conversation</p>
              <p className="text-xs mt-1">
                or start a new one with the + button
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Thread header */}
            <div className="px-6 py-4 bg-white border-b border-gray-200 flex items-center gap-3">
              <button
                onClick={() => setSelectedPhone(null)}
                className="md:hidden text-gray-500 hover:text-gray-700"
              >
                <ArrowLeft className="h-5 w-5" />
              </button>
              <div className="h-8 w-8 rounded-full bg-orange-100 flex items-center justify-center">
                <User className="h-4 w-4 text-orange-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {selectedPhone}
                </p>
                <p className="text-xs text-gray-500">SMS conversation</p>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
              {thread.isLoading ? (
                <div className="space-y-3">
                  {[...Array(4)].map((_, i) => (
                    <div
                      key={i}
                      className={clsx(
                        "h-12 bg-gray-200 animate-pulse rounded-lg w-2/3",
                        i % 2 === 0 ? "" : "ml-auto"
                      )}
                    />
                  ))}
                </div>
              ) : thread.data?.messages.length === 0 ? (
                <div className="flex-1 flex items-center justify-center py-12 text-gray-400">
                  <div className="text-center">
                    <MessageSquare className="h-8 w-8 mx-auto mb-2" />
                    <p className="text-sm">No messages yet</p>
                    <p className="text-xs mt-1">
                      Send the first message below
                    </p>
                  </div>
                </div>
              ) : (
                thread.data?.messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={clsx(
                      "flex gap-2 max-w-[80%]",
                      msg.direction === "outbound"
                        ? "ml-auto flex-row-reverse"
                        : ""
                    )}
                  >
                    <div
                      className={clsx(
                        "h-6 w-6 rounded-full flex items-center justify-center flex-shrink-0 mt-1",
                        msg.direction === "outbound"
                          ? "bg-orange-100"
                          : "bg-gray-200"
                      )}
                    >
                      {msg.sender_type === "agent" ? (
                        <Bot className="h-3 w-3 text-orange-600" />
                      ) : msg.direction === "outbound" ? (
                        <Send className="h-3 w-3 text-orange-600" />
                      ) : (
                        <User className="h-3 w-3 text-gray-600" />
                      )}
                    </div>
                    <div
                      className={clsx(
                        "rounded-lg px-3 py-2",
                        msg.direction === "outbound"
                          ? "bg-orange-600 text-white"
                          : "bg-white border border-gray-200 text-gray-900"
                      )}
                    >
                      <p className="text-sm">{msg.body || "(no content)"}</p>
                      <div
                        className={clsx(
                          "flex items-center gap-2 mt-1 text-xs",
                          msg.direction === "outbound"
                            ? "text-orange-200"
                            : "text-gray-400"
                        )}
                      >
                        <span>
                          {formatDistanceToNow(new Date(msg.created_at), {
                            addSuffix: true,
                          })}
                        </span>
                        {msg.agent_name && (
                          <span className="flex items-center gap-0.5">
                            <Bot className="h-3 w-3" />
                            {msg.agent_name}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Compose area */}
            <form
              onSubmit={handleSend}
              className="px-6 py-4 bg-white border-t border-gray-200"
            >
              {sendMutation.isError && (
                <p className="text-xs text-red-600 mb-2">
                  Failed to send. Your Twilio number may still be pending
                  verification.
                </p>
              )}
              <div className="flex items-end gap-3">
                <textarea
                  value={composeText}
                  onChange={(e) => setComposeText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend(e);
                    }
                  }}
                  placeholder="Type a message... (Enter to send)"
                  rows={1}
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500 resize-none"
                />
                <button
                  type="submit"
                  disabled={!composeText.trim() || sendMutation.isPending}
                  className="h-9 w-9 rounded-lg bg-orange-600 flex items-center justify-center text-white hover:bg-orange-700 disabled:opacity-50 transition-colors flex-shrink-0"
                >
                  {sendMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
