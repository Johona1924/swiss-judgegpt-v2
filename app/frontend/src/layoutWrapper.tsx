import { AccountInfo, EventType, PublicClientApplication } from "@azure/msal-browser";
import { checkLoggedIn, msalConfig, useLogin } from "./authConfig";
import { useEffect, useMemo, useState } from "react";
import { MsalProvider } from "@azure/msal-react";
import { LoginContext } from "./loginContext";
import Layout from "./pages/layout/Layout";

const LayoutWrapper = () => {
    const [loggedIn, setLoggedIn] = useState(false);
    const msalInstance = useMemo(() => {
        if (useLogin && msalConfig) {
            return new PublicClientApplication(msalConfig);
        }
        return undefined;
    }, []);

    useEffect(() => {
        if (msalInstance) {
            // Default to using the first account if no account is active on page load
            if (!msalInstance.getActiveAccount() && msalInstance.getAllAccounts().length > 0) {
                // Account selection logic is app dependent. Adjust as needed for different use cases.
                msalInstance.setActiveAccount(msalInstance.getAllAccounts()[0]);
            }

            // Listen for sign-in event and set active account
            const callbackId = msalInstance.addEventCallback(event => {
                if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
                    const account = event.payload as AccountInfo;
                    msalInstance.setActiveAccount(account);
                }
            });

            const fetchLoggedIn = async () => {
                setLoggedIn(await checkLoggedIn(msalInstance));
            };

            fetchLoggedIn();

            return () => {
                if (callbackId) {
                    msalInstance.removeEventCallback(callbackId);
                }
            };
        } else if (useLogin) {
            // Handle authentication without MSAL (e.g., Auth0, app services)
            const fetchLoggedIn = async () => {
                setLoggedIn(await checkLoggedIn(undefined));
            };

            fetchLoggedIn();
        }
    }, [msalInstance]);

    if (msalInstance) {
        return (
            <MsalProvider instance={msalInstance}>
                <LoginContext.Provider
                    value={{
                        loggedIn,
                        setLoggedIn
                    }}
                >
                    <Layout />
                </LoginContext.Provider>
            </MsalProvider>
        );
    } else {
        return (
            <LoginContext.Provider
                value={{
                    loggedIn,
                    setLoggedIn
                }}
            >
                <Layout />
            </LoginContext.Provider>
        );
    }
};

export default LayoutWrapper;
