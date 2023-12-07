import { HealthCheckBanner } from "@/components/health/healthcheck";
import { User } from "@/lib/types";
import {
  getCurrentUserSS,
  getAuthUrlSS,
  getAuthTypeMetadataSS,
  AuthTypeMetadata,
} from "@/lib/userSS";
import { redirect } from "next/navigation";
import { getWebVersion, getBackendVersion } from "@/lib/version";
import Image from "next/image";
import { SignInButton } from "./SignInButton";
import { FaUserCog } from "react-icons/fa";


const Page = async ({
  searchParams,
}: {
  searchParams?: { [key: string]: string | string[] | undefined };
}) => {
  const autoRedirectDisabled = searchParams?.disableAutoRedirect === "true";

  // catch cases where the backend is completely unreachable here
  // without try / catch, will just raise an exception and the page
  // will not render
  let authTypeMetadata: AuthTypeMetadata | null = null;
  let currentUser: User | null = null;
  try {
    [authTypeMetadata, currentUser] = await Promise.all([
      getAuthTypeMetadataSS(),
      getCurrentUserSS(),
    ]);
  } catch (e) {
    console.log(`Some fetch failed for the login page - ${e}`);
  }

  let web_version: string | null = null;
  let backend_version: string | null = null;
  try {
    [web_version, backend_version] = await Promise.all([
      getWebVersion(),
      getBackendVersion(),
    ]);
  } catch (e) {
    console.log(`Version info fetch failed for the login page - ${e}`);
  }

  // simply take the user to the home page if Auth is disabled
  if (authTypeMetadata?.authType === "disabled") {
    return redirect("/");
  }

  // if user is already logged in, take them to the main app page
  if (currentUser && currentUser.is_active && currentUser.is_verified) {
    return redirect("/");
  }

  // get where to send the user to authenticate
  let authUrl: string | null = null;
  if (authTypeMetadata) {
    try {
      authUrl = await getAuthUrlSS(authTypeMetadata.authType);
    } catch (e) {
      console.log(`Some fetch failed for the login page - ${e}`);
    }
  }

  if (authTypeMetadata?.autoRedirect && authUrl && !autoRedirectDisabled) {
    return redirect(authUrl);
  }

  return (
    <main>
      <div className="absolute top-10x w-full">
        <HealthCheckBanner />
      </div>
      <div className="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8" 
     style={{backgroundImage: "linear-gradient(rgb(122 253 255 / 99%), rgb(220 178 135 / 85%)), url(https://img.freepik.com/free-photo/elevated-view-coffee-cup-spiral-notepad-eyeglasses-laptop-mouse-blue-backdrop_23-2148178553.jpg?w=2000&t=st=1701293492~exp=1701294092~hmac=fbb47f76289804a0d278fc2ebc8f667998175d2ffd4ecb80da1dfb67a5109221)", 
             backgroundRepeat: "no-repeat",
             backgroundSize: "cover"}}>      
             
             
              <div>
          <div className="h-16 w-16 mx-auto mb-10">
           
          </div>
          {/* <h2 className="text-center text-xl font-bold mt-4 text-logo-darkblue-600 mb-16"> */}
            <img src="https://www.paysera.lt/v2/compiled/logo-white-v2.a529473ad77a993e276970c4fcceadc2.svg" width="250px" />
          {/* </h2> */}<br />
          <div className="text-center text-logo-darkblue-600 grid grid-cols-3 gap-5 pt-4">
            <div className="w-60 text-left">
              <FaUserCog className="text-3xl pb-2" />

              <h3 className="pb-2">What is PayserAi?</h3>
              <p className="text-xs">Paysera-ai revolutionizes the way enterprises interact with their internal documents. This advanced question-answering system allows users to pose questions in natural language and receive accurate, contextually relevant answers. These answers are not just generated responses but are backed by direct quotes and references from your Confluence content, ensuring reliability and trustworthiness.</p>
            </div>
            <div className="w-60 text-left">
              <FaUserCog className="text-3xl pb-2" />

              <h3 className="pb-2">Who are its Audiences?</h3>
              <p className="text-xs">Anyone who relies on Confluence for documentation, knowledge bases, or other content can ask the chatbot specific questions and receive direct answers or references to the relevant Confluence page.</p>
            </div>
            <div className="w-60 text-left">
              <FaUserCog className="text-3xl pb-2" />

              <h3 className="pb-2">How it works?</h3>
              <p className="text-xs">Question Input: How questions are received from the user interface or integrated services.
Document Search: The process of searching connected data sources for relevant documents.
AI Processing: How the generative AI models process the documents to generate answers.
Answer Output: The delivery of answers back to the user interface or the requesting service.</p>
            </div>
           



          </div>
          {authUrl && authTypeMetadata && (
            <SignInButton
              authorizeUrl={authUrl}
              authType={authTypeMetadata?.authType}
            />
          )}
        </div>
      </div>

      <div className="fixed bottom-4 right-4 z-50 text-logo-white p-2">
        {/* VERSION w{web_version} b{backend_version} */}
      </div>
    </main>
  );
};

export default Page;
