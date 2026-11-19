"use client";

import { AuthProvider } from "../components/auth-provider";
import { ApplicationFrame } from "../components/application-frame";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ApplicationFrame>{children}</ApplicationFrame>
    </AuthProvider>
  );
}
