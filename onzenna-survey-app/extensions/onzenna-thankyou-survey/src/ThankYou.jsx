import {
  reactExtension,
  BlockStack,
  InlineStack,
  Heading,
  Text,
  Select,
  TextField,
  Checkbox,
  Button,
  Banner,
  Link,
  Divider,
  useOrder,
  useSettings,
} from "@shopify/ui-extensions-react/checkout";
import { useState } from "react";

// Target: renders as a block on the thank-you page
export default reactExtension(
  "purchase.thank-you.block.render",
  () => <ThankYouSurvey />
);

function ThankYouSurvey() {
  const order = useOrder();
  const settings = useSettings();

  // Read is_creator from order metafields
  // Note: On the thank-you page, we read from the order's note attributes
  // or metafields that were set during checkout
  const orderMetafields = order?.metafields || [];
  const isCreatorMf = orderMetafields.find(
    (m) => m.namespace === "onzenna_survey" && m.key === "is_creator"
  );
  const isCreator = isCreatorMf?.value === "true";

  const loyaltyPageUrl = settings?.loyalty_page_url || "/pages/loyalty-survey";

  return (
    <BlockStack spacing="loose">
      {isCreator ? (
        <CreatorBranchForm
          order={order}
          webhookUrl={settings?.n8n_webhook_url}
          loyaltyPageUrl={loyaltyPageUrl}
        />
      ) : (
        <LoyaltyCTA loyaltyPageUrl={loyaltyPageUrl} />
      )}
    </BlockStack>
  );
}

// ---------------------------------------------------------------------------
// Creator Branch Form (Part 2)
// ---------------------------------------------------------------------------
function CreatorBranchForm({ order, webhookUrl, loyaltyPageUrl }) {
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Form state
  const [primaryPlatform, setPrimaryPlatform] = useState("");
  const [primaryHandle, setPrimaryHandle] = useState("");
  const [hasOtherChannels, setHasOtherChannels] = useState(false);
  const [otherPlatform1, setOtherPlatform1] = useState("");
  const [otherHandle1, setOtherHandle1] = useState("");
  const [otherPlatform2, setOtherPlatform2] = useState("");
  const [otherHandle2, setOtherHandle2] = useState("");
  const [otherPlatform3, setOtherPlatform3] = useState("");
  const [otherHandle3, setOtherHandle3] = useState("");
  const [followingSize, setFollowingSize] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [contentTypes, setContentTypes] = useState({
    reviews: false,
    day_in_the_life: false,
    educational: false,
    humor: false,
    aesthetic_lifestyle: false,
  });
  const [hasBrandPartnerships, setHasBrandPartnerships] = useState(false);

  const platformOptions = [
    { value: "", label: "Select platform..." },
    { value: "instagram", label: "Instagram" },
    { value: "tiktok", label: "TikTok" },
    { value: "youtube", label: "YouTube" },
    { value: "pinterest", label: "Pinterest" },
    { value: "blog", label: "Blog" },
  ];

  const handleSubmit = async () => {
    if (!primaryPlatform || !primaryHandle) return;

    setSubmitting(true);

    const selectedContentTypes = Object.entries(contentTypes)
      .filter(([_, v]) => v)
      .map(([k]) => k);

    const otherPlatforms = [];
    if (otherPlatform1 && otherHandle1)
      otherPlatforms.push({ platform: otherPlatform1, handle: otherHandle1 });
    if (otherPlatform2 && otherHandle2)
      otherPlatforms.push({ platform: otherPlatform2, handle: otherHandle2 });
    if (otherPlatform3 && otherHandle3)
      otherPlatforms.push({ platform: otherPlatform3, handle: otherHandle3 });

    const payload = {
      form_type: "onzenna_creator_survey",
      order_id: order?.id,
      customer_id: order?.customer?.id,
      submitted_at: new Date().toISOString(),
      creator_data: {
        primary_platform: primaryPlatform,
        primary_handle: primaryHandle,
        other_platforms: otherPlatforms,
        following_size: followingSize,
        hashtags: hashtags,
        content_type: selectedContentTypes,
        has_brand_partnerships: hasBrandPartnerships,
      },
    };

    try {
      if (webhookUrl) {
        await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      setSubmitted(true);
    } catch (err) {
      console.error("Creator survey submit error:", err);
      // Still mark as submitted to avoid blocking the thank-you page
      setSubmitted(true);
    }

    setSubmitting(false);
  };

  if (submitted) {
    return (
      <BlockStack spacing="base">
        <Banner status="success">
          Thanks for sharing your creator profile!
        </Banner>
        <LoyaltyCTA loyaltyPageUrl={loyaltyPageUrl} />
      </BlockStack>
    );
  }

  return (
    <BlockStack spacing="base">
      <Heading level={2}>You're a creator!</Heading>
      <Text size="small" appearance="subdued">
        Tell us more about your content so we can collaborate with you.
      </Text>

      {/* Q1: Primary Platform */}
      <Select
        label="What platform are you most active on?"
        options={platformOptions}
        value={primaryPlatform}
        onChange={setPrimaryPlatform}
      />

      {/* Q2: Primary Handle */}
      <TextField
        label="Your handle on that platform"
        placeholder="@yourhandle"
        value={primaryHandle}
        onChange={setPrimaryHandle}
      />

      {/* Q3: Other Channels */}
      <Checkbox value={hasOtherChannels} onChange={setHasOtherChannels}>
        I have other channels
      </Checkbox>

      {hasOtherChannels && (
        <BlockStack spacing="tight">
          <InlineStack spacing="base">
            <Select
              label="Platform"
              options={platformOptions}
              value={otherPlatform1}
              onChange={setOtherPlatform1}
            />
            <TextField
              label="Handle"
              placeholder="@handle"
              value={otherHandle1}
              onChange={setOtherHandle1}
            />
          </InlineStack>
          <InlineStack spacing="base">
            <Select
              label="Platform"
              options={platformOptions}
              value={otherPlatform2}
              onChange={setOtherPlatform2}
            />
            <TextField
              label="Handle"
              placeholder="@handle"
              value={otherHandle2}
              onChange={setOtherHandle2}
            />
          </InlineStack>
          <InlineStack spacing="base">
            <Select
              label="Platform"
              options={platformOptions}
              value={otherPlatform3}
              onChange={setOtherPlatform3}
            />
            <TextField
              label="Handle"
              placeholder="@handle"
              value={otherHandle3}
              onChange={setOtherHandle3}
            />
          </InlineStack>
        </BlockStack>
      )}

      {/* Q4: Following Size */}
      <Select
        label="Approximate following size (primary platform)"
        options={[
          { value: "", label: "Select range..." },
          { value: "under_1k", label: "Under 1K" },
          { value: "1k_10k", label: "1K - 10K" },
          { value: "10k_50k", label: "10K - 50K" },
          { value: "50k_plus", label: "50K+" },
        ]}
        value={followingSize}
        onChange={setFollowingSize}
      />

      {/* Q5: Hashtags */}
      <TextField
        label="What hashtags do you typically use?"
        placeholder="#newmom, #babygear, #momlife"
        value={hashtags}
        onChange={setHashtags}
      />

      {/* Q6: Content Type */}
      <BlockStack spacing="tight">
        <Text size="small">What kind of content do you make?</Text>
        <Checkbox
          value={contentTypes.reviews}
          onChange={(v) =>
            setContentTypes((prev) => ({ ...prev, reviews: v }))
          }
        >
          Product reviews
        </Checkbox>
        <Checkbox
          value={contentTypes.day_in_the_life}
          onChange={(v) =>
            setContentTypes((prev) => ({ ...prev, day_in_the_life: v }))
          }
        >
          Day-in-the-life
        </Checkbox>
        <Checkbox
          value={contentTypes.educational}
          onChange={(v) =>
            setContentTypes((prev) => ({ ...prev, educational: v }))
          }
        >
          Educational
        </Checkbox>
        <Checkbox
          value={contentTypes.humor}
          onChange={(v) =>
            setContentTypes((prev) => ({ ...prev, humor: v }))
          }
        >
          Humor
        </Checkbox>
        <Checkbox
          value={contentTypes.aesthetic_lifestyle}
          onChange={(v) =>
            setContentTypes((prev) => ({
              ...prev,
              aesthetic_lifestyle: v,
            }))
          }
        >
          Aesthetic / Lifestyle
        </Checkbox>
      </BlockStack>

      {/* Q7: Brand Partnerships */}
      <Checkbox
        value={hasBrandPartnerships}
        onChange={setHasBrandPartnerships}
      >
        I'm currently working with baby or parenting brands
      </Checkbox>

      <Button
        kind="secondary"
        onPress={handleSubmit}
        loading={submitting}
        disabled={!primaryPlatform || !primaryHandle}
      >
        Submit Creator Profile
      </Button>
    </BlockStack>
  );
}

// ---------------------------------------------------------------------------
// Loyalty CTA Banner (shown to everyone)
// ---------------------------------------------------------------------------
function LoyaltyCTA({ loyaltyPageUrl }) {
  return (
    <BlockStack spacing="tight">
      <Divider />
      <Banner status="info">
        <BlockStack spacing="extraTight">
          <Text emphasis="bold">Get 10% off your next order!</Text>
          <Text size="small">
            Complete a quick 6-question survey about your preferences and
            unlock an exclusive discount code.
          </Text>
          <Link to={loyaltyPageUrl}>Take the survey →</Link>
        </BlockStack>
      </Banner>
    </BlockStack>
  );
}
