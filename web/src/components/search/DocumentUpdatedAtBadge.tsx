import { timeAgo } from "@/lib/time";

export function DocumentUpdatedAtBadge({ updatedAt }: { updatedAt: string }) {
  return (
    <div className="flex flex-wrap gap-x-2 mt-1">
      <div
        className={`
    text-xs 
    text-lightblue-600
    rounded 
    px-1
    py-0.5 
    w-fit 
    my-auto 
    select-none 
    mr-2`}
      >
        <div className="mr-1 my-auto flex text-logo-darkblue-600">
          {"Updated " + timeAgo(updatedAt)}
        </div>
      </div>
    </div>
  );
}
