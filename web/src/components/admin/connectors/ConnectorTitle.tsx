import { getSourceMetadata } from "@/components/source";
import {
  ConfluenceConfig,
  Connector,
  ConnectorIndexingStatus,
  GithubConfig,
  GoogleDriveConfig,
  JiraConfig,
  SlackConfig,
  WebConfig,
  ZulipConfig,
} from "@/lib/types";
import Link from "next/link";

interface ConnectorTitleProps {
  connector: Connector<any>;
  ccPairId: number;
  ccPairName: string | null | undefined;
  isPublic?: boolean;
  owner?: string;
  isLink?: boolean;
  showMetadata?: boolean;
}

export const ConnectorTitle = ({
  connector,
  ccPairId,
  ccPairName,
  owner,
  isPublic = true,
  isLink = true,
  showMetadata = true,
}: ConnectorTitleProps) => {
  const sourceMetadata = getSourceMetadata(connector.source);

  let additionalMetadata = connector.getAdditionalMetadata(isPublic, owner);

  const mainSectionClassName = "text-blue-500 flex w-fit";
  const mainDisplay = (
    <>
      {sourceMetadata.icon({ size: 20 })}
      <div className="ml-1 my-auto">
        {ccPairName || sourceMetadata.displayName}
      </div>
    </>
  );
  return (
    <div>
      {isLink ? (
        <Link
          className={mainSectionClassName}
          href={`/admin/connector/${ccPairId}`}
        >
          {mainDisplay}
        </Link>
      ) : (
        <div className={mainSectionClassName}>{mainDisplay}</div>
      )}
      {showMetadata && (
        <div className="text-xs text-gray-400 mt-1">
          {Array.from(additionalMetadata.entries()).map(([key, value]) => {
            return (
              <div key={key}>
                <i>{key}:</i> {value}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
