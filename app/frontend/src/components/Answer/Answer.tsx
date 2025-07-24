import { useMemo, useState, FormEvent, useEffect } from "react";
import { Stack, IconButton, Dialog, DefaultButton, Text, Checkbox } from "@fluentui/react";
import { ThumbLike20Filled, ThumbDislike20Filled } from "@fluentui/react-icons";
import { useTranslation } from "react-i18next";
import DOMPurify from "dompurify";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

import styles from "./Answer.module.css";
import { ChatAppResponse, getCitationFilePath, SpeechConfig, Feedback, messageFeedbackApi } from "../../api";
import { parseAnswerToHtml } from "./AnswerParser";
import { AnswerIcon } from "./AnswerIcon";
import { SpeechOutputBrowser } from "./SpeechOutputBrowser";
import { SpeechOutputAzure } from "./SpeechOutputAzure";
import { getToken } from "../../authConfig";
import { useMsal } from "@azure/msal-react";

interface Props {
    answer: ChatAppResponse;
    index: number;
    speechConfig: SpeechConfig;
    isSelected?: boolean;
    isStreaming: boolean;
    onCitationClicked: (filePath: string) => void;
    onThoughtProcessClicked: () => void;
    onSupportingContentClicked: () => void;
    onFollowupQuestionClicked?: (question: string) => void;
    showFollowupQuestions?: boolean;
    showSpeechOutputBrowser?: boolean;
    showSpeechOutputAzure?: boolean;
    sessionId?: string;
    onFeedbackUpdated?: (messageIndex: number, feedback: Feedback) => void;
}

export const Answer = ({
    answer,
    index,
    speechConfig,
    isSelected,
    isStreaming,
    onCitationClicked,
    onThoughtProcessClicked,
    onSupportingContentClicked,
    onFollowupQuestionClicked,
    showFollowupQuestions,
    showSpeechOutputAzure,
    showSpeechOutputBrowser,
    sessionId,
    onFeedbackUpdated
}: Props) => {
    const followupQuestions = answer.context?.followup_questions;
    const parsedAnswer = useMemo(() => parseAnswerToHtml(answer, isStreaming, onCitationClicked), [answer]);
    const { t } = useTranslation();
    const sanitizedAnswerHtml = DOMPurify.sanitize(parsedAnswer.answerHtml);
    const [copied, setCopied] = useState(false);
    
    // Feedback state
    const [feedbackState, setFeedbackState] = useState<Feedback>(answer.feedback || Feedback.Neutral);
    const [isFeedbackDialogOpen, setIsFeedbackDialogOpen] = useState(false);
    const [showReportInappropriateFeedback, setShowReportInappropriateFeedback] = useState(false);
    const [negativeFeedbackList, setNegativeFeedbackList] = useState<Feedback[]>([]);
    
    // Sync feedback state when answer prop changes
    useEffect(() => {
        setFeedbackState(answer.feedback || Feedback.Neutral);
    }, [answer.feedback]);
    
    const { instance } = useMsal();

    const handleCopy = () => {
        // Single replace to remove all HTML tags to remove the citations
        const textToCopy = sanitizedAnswerHtml.replace(/<a [^>]*><sup>\d+<\/sup><\/a>|<[^>]+>/g, "");

        navigator.clipboard
            .writeText(textToCopy)
            .then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
            })
            .catch(err => console.error("Failed to copy text: ", err));
    };

    const onLikeResponseClicked = async () => {
        if (!sessionId) return;

        let newFeedbackState = feedbackState;
        // Set or unset the thumbs up state
        if (feedbackState === Feedback.Positive) {
            newFeedbackState = Feedback.Neutral;
        } else {
            newFeedbackState = Feedback.Positive;
        }
        
        setFeedbackState(newFeedbackState);
        onFeedbackUpdated?.(index, newFeedbackState);

        try {
            const token = await getToken(instance);
            await messageFeedbackApi(sessionId, index, newFeedbackState, token || "");
        } catch (error) {
            console.error("Failed to update feedback:", error);
            // Revert state on error
            setFeedbackState(feedbackState);
            onFeedbackUpdated?.(index, feedbackState);
        }
    };

    const onDislikeResponseClicked = async () => {
        if (!sessionId) return;

        let newFeedbackState = feedbackState;
        if (feedbackState === Feedback.Neutral || feedbackState === Feedback.Positive) {
            newFeedbackState = Feedback.Negative;
            setFeedbackState(newFeedbackState);
            setIsFeedbackDialogOpen(true);
        } else {
            // Reset negative feedback to neutral
            newFeedbackState = Feedback.Neutral;
            setFeedbackState(newFeedbackState);
            onFeedbackUpdated?.(index, newFeedbackState);
            
            try {
                const token = await getToken(instance);
                await messageFeedbackApi(sessionId, index, Feedback.Neutral, token || "");
            } catch (error) {
                console.error("Failed to update feedback:", error);
                // Revert state on error
                setFeedbackState(feedbackState);
                onFeedbackUpdated?.(index, feedbackState);
            }
        }
    };

    const updateFeedbackList = (ev?: FormEvent<HTMLElement | HTMLInputElement>, checked?: boolean) => {
        const selectedFeedback = (ev?.target as HTMLInputElement)?.id as Feedback;

        let feedbackList = negativeFeedbackList.slice();
        if (checked) {
            feedbackList.push(selectedFeedback);
        } else {
            feedbackList = feedbackList.filter(f => f !== selectedFeedback);
        }

        setNegativeFeedbackList(feedbackList);
    };

    const onSubmitNegativeFeedback = async () => {
        if (!sessionId) return;
        
        const feedbackValue = negativeFeedbackList.join(',');
        onFeedbackUpdated?.(index, Feedback.Negative);
        
        try {
            const token = await getToken(instance);
            await messageFeedbackApi(sessionId, index, feedbackValue, token || "");
            resetFeedbackDialog();
        } catch (error) {
            console.error("Failed to update feedback:", error);
            // Revert state on error
            setFeedbackState(feedbackState);
            onFeedbackUpdated?.(index, feedbackState);
        }
    };

    const resetFeedbackDialog = () => {
        setIsFeedbackDialogOpen(false);
        setShowReportInappropriateFeedback(false);
        setNegativeFeedbackList([]);
    };

    const UnhelpfulFeedbackContent = () => {
        return (
            <>
                <div>Why wasn't this response helpful?</div>
                <Stack tokens={{ childrenGap: 4 }}>
                    <Checkbox
                        label="Citations are missing"
                        id={Feedback.MissingCitation}
                        defaultChecked={negativeFeedbackList.includes(Feedback.MissingCitation)}
                        onChange={updateFeedbackList}
                    />
                    <Checkbox
                        label="Citations are wrong"
                        id={Feedback.WrongCitation}
                        defaultChecked={negativeFeedbackList.includes(Feedback.WrongCitation)}
                        onChange={updateFeedbackList}
                    />
                    <Checkbox
                        label="The response is not from my data"
                        id={Feedback.OutOfScope}
                        defaultChecked={negativeFeedbackList.includes(Feedback.OutOfScope)}
                        onChange={updateFeedbackList}
                    />
                    <Checkbox
                        label="Inaccurate or irrelevant"
                        id={Feedback.InaccurateOrIrrelevant}
                        defaultChecked={negativeFeedbackList.includes(Feedback.InaccurateOrIrrelevant)}
                        onChange={updateFeedbackList}
                    />
                    <Checkbox
                        label="Other"
                        id={Feedback.OtherUnhelpful}
                        defaultChecked={negativeFeedbackList.includes(Feedback.OtherUnhelpful)}
                        onChange={updateFeedbackList}
                    />
                </Stack>
                <div onClick={() => setShowReportInappropriateFeedback(true)} style={{ color: '#115EA3', cursor: 'pointer' }}>
                    Report inappropriate content
                </div>
            </>
        );
    };

    const ReportInappropriateFeedbackContent = () => {
        return (
            <>
                <div>
                    The content is <span style={{ color: 'red' }}>*</span>
                </div>
                <Stack tokens={{ childrenGap: 4 }}>
                    <Checkbox
                        label="Hate speech, stereotyping, demeaning"
                        id={Feedback.HateSpeech}
                        defaultChecked={negativeFeedbackList.includes(Feedback.HateSpeech)}
                        onChange={updateFeedbackList}
                    />
                    <Checkbox
                        label="Violent: glorification of violence, self-harm"
                        id={Feedback.Violent}
                        defaultChecked={negativeFeedbackList.includes(Feedback.Violent)}
                        onChange={updateFeedbackList}
                    />
                    <Checkbox
                        label="Sexual: explicit content, grooming"
                        id={Feedback.Sexual}
                        defaultChecked={negativeFeedbackList.includes(Feedback.Sexual)}
                        onChange={updateFeedbackList}
                    />
                    <Checkbox
                        label="Manipulative: devious, emotional, pushy, bullying"
                        defaultChecked={negativeFeedbackList.includes(Feedback.Manipulative)}
                        id={Feedback.Manipulative}
                        onChange={updateFeedbackList}
                    />
                    <Checkbox
                        label="Other"
                        id={Feedback.OtherHarmful}
                        defaultChecked={negativeFeedbackList.includes(Feedback.OtherHarmful)}
                        onChange={updateFeedbackList}
                    />
                </Stack>
            </>
        );
    };

    return (
        <>
            <Stack className={`${styles.answerContainer} ${isSelected && styles.selected}`} verticalAlign="space-between">
                <Stack.Item>
                    <Stack horizontal horizontalAlign="space-between">
                        <AnswerIcon />
                        <div>
                            <IconButton
                                style={{ color: "black" }}
                                iconProps={{ iconName: copied ? "CheckMark" : "Copy" }}
                                title={copied ? t("tooltips.copied") : t("tooltips.copy")}
                                ariaLabel={copied ? t("tooltips.copied") : t("tooltips.copy")}
                                onClick={handleCopy}
                            />
                            <IconButton
                                style={{ color: "black" }}
                                iconProps={{ iconName: "Lightbulb" }}
                                title={t("tooltips.showThoughtProcess")}
                                ariaLabel={t("tooltips.showThoughtProcess")}
                                onClick={() => onThoughtProcessClicked()}
                                disabled={!answer.context.thoughts?.length || isStreaming}
                            />
                            <IconButton
                                style={{ color: "black" }}
                                iconProps={{ iconName: "ClipboardList" }}
                                title={t("tooltips.showSupportingContent")}
                                ariaLabel={t("tooltips.showSupportingContent")}
                                onClick={() => onSupportingContentClicked()}
                                disabled={!answer.context.data_points || isStreaming}
                            />
                            {sessionId && !isStreaming && (
                                <>
                                    <ThumbLike20Filled
                                        aria-hidden="false"
                                        aria-label="Like this response"
                                        onClick={() => onLikeResponseClicked()}
                                        style={
                                            feedbackState === Feedback.Positive
                                                ? { color: 'darkgreen', cursor: 'pointer', marginLeft: '8px' }
                                                : { color: 'slategray', cursor: 'pointer', marginLeft: '8px' }
                                        }
                                    />
                                    <ThumbDislike20Filled
                                        aria-hidden="false"
                                        aria-label="Dislike this response"
                                        onClick={() => onDislikeResponseClicked()}
                                        style={
                                            feedbackState !== Feedback.Positive &&
                                            feedbackState !== Feedback.Neutral
                                                ? { color: 'darkred', cursor: 'pointer', marginLeft: '8px' }
                                                : { color: 'slategray', cursor: 'pointer', marginLeft: '8px' }
                                        }
                                    />
                                </>
                            )}
                            {showSpeechOutputAzure && (
                                <SpeechOutputAzure answer={sanitizedAnswerHtml} index={index} speechConfig={speechConfig} isStreaming={isStreaming} />
                            )}
                            {showSpeechOutputBrowser && <SpeechOutputBrowser answer={sanitizedAnswerHtml} />}
                        </div>
                    </Stack>
                </Stack.Item>

                <Stack.Item grow>
                    <div className={styles.answerText}>
                        <ReactMarkdown children={sanitizedAnswerHtml} rehypePlugins={[rehypeRaw]} remarkPlugins={[remarkGfm]} />
                    </div>
                </Stack.Item>

                {!!parsedAnswer.citations.length && (
                    <Stack.Item>
                        <Stack horizontal wrap tokens={{ childrenGap: 5 }}>
                            <span className={styles.citationLearnMore}>{t("citationWithColon")}</span>
                            {parsedAnswer.citations.map((x, i) => {
                                const path = getCitationFilePath(x);
                                return (
                                    <a key={i} className={styles.citation} title={x} onClick={() => onCitationClicked(path)}>
                                        {`${++i}. ${x}`}
                                    </a>
                                );
                            })}
                        </Stack>
                    </Stack.Item>
                )}

                {!!followupQuestions?.length && showFollowupQuestions && onFollowupQuestionClicked && (
                    <Stack.Item>
                        <Stack horizontal wrap className={`${!!parsedAnswer.citations.length ? styles.followupQuestionsList : ""}`} tokens={{ childrenGap: 6 }}>
                            <span className={styles.followupQuestionLearnMore}>{t("followupQuestions")}</span>
                            {followupQuestions.map((x, i) => {
                                return (
                                    <a key={i} className={styles.followupQuestion} title={x} onClick={() => onFollowupQuestionClicked(x)}>
                                        {`${x}`}
                                    </a>
                                );
                            })}
                        </Stack>
                    </Stack.Item>
                )}
            </Stack>
            
            <Dialog
                onDismiss={() => {
                    resetFeedbackDialog();
                    setFeedbackState(Feedback.Neutral);
                }}
                hidden={!isFeedbackDialogOpen}
                styles={{
                    main: [
                        {
                            selectors: {
                                ['@media (min-width: 480px)']: {
                                    maxWidth: '600px',
                                    background: '#FFFFFF',
                                    boxShadow: '0px 14px 28.8px rgba(0, 0, 0, 0.24), 0px 0px 8px rgba(0, 0, 0, 0.2)',
                                    borderRadius: '8px',
                                    maxHeight: '600px',
                                    minHeight: '100px'
                                }
                            }
                        }
                    ]
                }}
                dialogContentProps={{
                    title: 'Submit Feedback',
                    showCloseButton: true
                }}>
                <Stack tokens={{ childrenGap: 4 }}>
                    <div>Your feedback will improve this experience.</div>

                    {!showReportInappropriateFeedback ? <UnhelpfulFeedbackContent /> : <ReportInappropriateFeedbackContent />}

                    <div>By pressing submit, your feedback will be visible to the application owner.</div>

                    <DefaultButton disabled={negativeFeedbackList.length < 1} onClick={onSubmitNegativeFeedback}>
                        Submit
                    </DefaultButton>
                </Stack>
            </Dialog>
        </>
    );
};
