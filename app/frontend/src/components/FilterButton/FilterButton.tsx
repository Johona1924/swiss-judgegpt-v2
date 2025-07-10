import { Filter24Regular } from "@fluentui/react-icons";
import { Button } from "@fluentui/react-components";
import { useTranslation } from "react-i18next";

import styles from "./FilterButton.module.css";

interface Props {
    className?: string;
    onClick: () => void;
}

export const FilterButton = ({ className, onClick }: Props) => {
    const { t } = useTranslation();
    return (
        <div className={`${styles.container} ${className ?? ""}`}>
            <Button icon={<Filter24Regular />} onClick={onClick}>
                {t("filters")}
            </Button>
        </div>
    );
};
