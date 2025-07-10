import { TextField } from "@fluentui/react";
import { useTranslation } from "react-i18next";

import styles from "./Filters.module.css";

export interface FiltersProps {
    className?: string;
    yearFrom?: number;
    yearTo?: number;
    onChange: (field: string, value: any) => void;
}

export const Filters = ({ className, yearFrom, yearTo, onChange }: FiltersProps) => {
    const { t } = useTranslation();

    return (
        <div className={className}>
            <div className={styles.settingsSeparator}>
                <h3>{t("labels.filterByYear")}</h3>
                <div className={styles.yearFilterContainer}>
                    <TextField
                        label={t("labels.yearFrom")}
                        type="number"
                        value={yearFrom ? yearFrom.toString() : ""}
                        onChange={(ev, newValue) => {
                            const value = newValue ? parseInt(newValue) : undefined;
                            onChange("yearFrom", value);
                        }}
                        placeholder={t("labels.yearFromPlaceholder")}
                    />
                    <TextField
                        label={t("labels.yearTo")}
                        type="number"
                        value={yearTo ? yearTo.toString() : ""}
                        onChange={(ev, newValue) => {
                            const value = newValue ? parseInt(newValue) : undefined;
                            onChange("yearTo", value);
                        }}
                        placeholder={t("labels.yearToPlaceholder")}
                    />
                </div>
            </div>
        </div>
    );
};
