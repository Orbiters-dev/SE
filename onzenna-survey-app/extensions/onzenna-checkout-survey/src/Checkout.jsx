import {
  reactExtension,
  BlockStack,
  Heading,
  Select,
  TextField,
  Checkbox,
  Text,
  InlineStack,
  useApplyMetafieldsChange,
  useMetafield,
  useCustomer,
} from "@shopify/ui-extensions-react/checkout";

// Target: renders after the contact info section in checkout
export default reactExtension(
  "purchase.checkout.contact.render-after",
  () => <OnzennaSurvey />
);

function OnzennaSurvey() {
  const applyMetafieldsChange = useApplyMetafieldsChange();
  const customer = useCustomer();

  // Check if customer already completed the survey (returning customer)
  const existingSignup = useMetafield({
    namespace: "onzenna_survey",
    key: "signup_completed_at",
  });

  // If already completed, don't show the survey
  if (existingSignup?.value) {
    return (
      <BlockStack spacing="tight">
        <Text size="small" appearance="subdued">
          Welcome back! We already have your preferences on file.
        </Text>
      </BlockStack>
    );
  }

  return (
    <BlockStack spacing="base">
      <Heading level={2}>Tell us about you</Heading>
      <Text size="small" appearance="subdued">
        Help us personalize your experience (optional)
      </Text>

      {/* Q4: Journey Stage */}
      <JourneyStageSelect applyMetafieldsChange={applyMetafieldsChange} />

      {/* Q5: Baby Birth Month */}
      <BabyBirthMonthPicker applyMetafieldsChange={applyMetafieldsChange} />

      {/* Q6: Other Children */}
      <OtherChildrenSection applyMetafieldsChange={applyMetafieldsChange} />

      {/* Q7: Content Creator */}
      <CreatorInterestCheckbox applyMetafieldsChange={applyMetafieldsChange} />
    </BlockStack>
  );
}

// ---------------------------------------------------------------------------
// Q4: Journey Stage
// ---------------------------------------------------------------------------
function JourneyStageSelect({ applyMetafieldsChange }) {
  const handleChange = (value) => {
    applyMetafieldsChange({
      type: "updateMetafield",
      namespace: "onzenna_survey",
      key: "journey_stage",
      valueType: "string",
      value: value,
    });
  };

  return (
    <Select
      label="Where are you in your journey?"
      options={[
        { value: "", label: "Select one..." },
        { value: "trying_to_conceive", label: "Trying to conceive" },
        { value: "pregnant", label: "Pregnant" },
        { value: "new_mom_0_12m", label: "New mom (0-12 months)" },
        { value: "mom_toddler_1_3y", label: "Mom of a toddler (1-3 years)" },
      ]}
      onChange={handleChange}
    />
  );
}

// ---------------------------------------------------------------------------
// Q5: Baby Birth Month + Year
// ---------------------------------------------------------------------------
function BabyBirthMonthPicker({ applyMetafieldsChange }) {
  const currentYear = new Date().getFullYear();

  const monthOptions = [
    { value: "", label: "Month" },
    { value: "01", label: "January" },
    { value: "02", label: "February" },
    { value: "03", label: "March" },
    { value: "04", label: "April" },
    { value: "05", label: "May" },
    { value: "06", label: "June" },
    { value: "07", label: "July" },
    { value: "08", label: "August" },
    { value: "09", label: "September" },
    { value: "10", label: "October" },
    { value: "11", label: "November" },
    { value: "12", label: "December" },
  ];

  // Years: from 3 years ago to 1 year in the future (covers toddlers + expecting)
  const yearOptions = [{ value: "", label: "Year" }];
  for (let y = currentYear + 1; y >= currentYear - 4; y--) {
    yearOptions.push({ value: String(y), label: String(y) });
  }

  // Store both as a combined YYYY-MM value
  let selectedMonth = "";
  let selectedYear = "";

  const updateMetafield = () => {
    if (selectedMonth && selectedYear) {
      applyMetafieldsChange({
        type: "updateMetafield",
        namespace: "onzenna_survey",
        key: "baby_birth_month",
        valueType: "string",
        value: `${selectedYear}-${selectedMonth}`,
      });
    }
  };

  return (
    <BlockStack spacing="tight">
      <Text size="small">Baby's birth month and year (or due date)</Text>
      <InlineStack spacing="base">
        <Select
          label="Month"
          options={monthOptions}
          onChange={(val) => {
            selectedMonth = val;
            updateMetafield();
          }}
        />
        <Select
          label="Year"
          options={yearOptions}
          onChange={(val) => {
            selectedYear = val;
            updateMetafield();
          }}
        />
      </InlineStack>
    </BlockStack>
  );
}

// ---------------------------------------------------------------------------
// Q6: Other Children
// ---------------------------------------------------------------------------
function OtherChildrenSection({ applyMetafieldsChange }) {
  let hasOther = false;

  return (
    <BlockStack spacing="tight">
      <Checkbox
        onChange={(checked) => {
          hasOther = checked;
          applyMetafieldsChange({
            type: "updateMetafield",
            namespace: "onzenna_survey",
            key: "has_other_children",
            valueType: "string",
            value: String(checked),
          });
        }}
      >
        I have other children
      </Checkbox>
      <TextField
        label="How many and how old?"
        placeholder="e.g., 2 kids: 3 years, 5 years"
        onChange={(val) => {
          if (val) {
            applyMetafieldsChange({
              type: "updateMetafield",
              namespace: "onzenna_survey",
              key: "other_children_detail",
              valueType: "string",
              value: val,
            });
          }
        }}
      />
    </BlockStack>
  );
}

// ---------------------------------------------------------------------------
// Q7: Content Creator Interest
// ---------------------------------------------------------------------------
function CreatorInterestCheckbox({ applyMetafieldsChange }) {
  return (
    <Checkbox
      onChange={(checked) => {
        applyMetafieldsChange({
          type: "updateMetafield",
          namespace: "onzenna_survey",
          key: "is_creator",
          valueType: "string",
          value: String(checked),
        });

        // Also set the completion timestamp
        applyMetafieldsChange({
          type: "updateMetafield",
          namespace: "onzenna_survey",
          key: "signup_completed_at",
          valueType: "string",
          value: new Date().toISOString(),
        });
      }}
    >
      I'm a content creator (or interested in becoming one)
    </Checkbox>
  );
}
