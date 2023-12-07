import { Header } from "@/components/Header";
import { Sidebar } from "@/components/admin/connectors/Sidebar";
import {
  NotebookIcon,
  KeyIcon,
  ConfluenceIcon,
  UsersIcon,

} from "@/components/icons/icons";
import { getAuthDisabledSS, getCurrentUserSS } from "@/lib/userSS";
import { redirect } from "next/navigation";

export async function Layout({ children }: { children: React.ReactNode }) {
  const [authDisabled, user] = await Promise.all([
    getAuthDisabledSS(),
    getCurrentUserSS(),
  ]);

  if (!authDisabled) {
    if (!user) {
      return redirect("/auth/login");
    }
    if (user.role !== "admin") {
      return redirect("/");
    }
  }

  return (
    <div>
      <Header user={user} />
      <div className="bg-gray-900 flex">
        <Sidebar
          title="Connector"
          collections={[
            {
              name: "Indexing",
              items: [
                {
                  name: (
                    <div className="flex">
                      <NotebookIcon size={18} />
                      <div className="ml-1">Status</div>
                    </div>
                  ),
                  link: "/admin/indexing/status",
                },
              ],
            },
            {
              name: "Connector Settings",
              items: [
              
                {
                  name: (
                    <div className="flex">
                      <ConfluenceIcon size={16} />
                      <div className="ml-1">Confluence</div>
                    </div>
                  ),
                  link: "/admin/connectors/confluence",
                }
              ],
            },
            {
              name: "Keys",
              items: [
                {
                  name: (
                    <div className="flex">
                      <KeyIcon size={18} />
                      <div className="ml-1">OpenAI</div>
                    </div>
                  ),
                  link: "/admin/keys/openai",
                },
              ],
            },
            {
              name: "User Management",
              items: [
                {
                  name: (
                    <div className="flex">
                      <UsersIcon size={18} />
                      <div className="ml-1">Users</div>
                    </div>
                  ),
                  link: "/admin/users",
                },
              ],
            },
          ]}
        />
        <div className="px-12 min-h-screen bg-logo-lightblue-200 text-logo-darkblue-600 w-full py-8">
          {children}
        </div>
      </div>
    </div>
  );
}
