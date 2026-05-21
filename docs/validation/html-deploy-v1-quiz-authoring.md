# html-deploy-v1 Quiz Authoring Guide

Decision: quiz templates must declare the quiz answer model before deployment. The deployer should not guess which option text belongs to a click, which path the validator should take, or how to reconstruct answer visibility after traffic starts.

## What To Declare

Every quiz page needs:

- `quizId`, `quizVersion`, and `quizVariant`
- one `quizQuestions[]` target per production question
- one `quizOptions[]` target per answer option that can be tracked
- `selectionOrder` on the option or options the validator should click
- optional `quizSubmissions[]` targets for multi-select or next-button style questions
- final CTA/binding metadata for the quiz-to-sales handoff

## Minimal Single-Select Example

```json
{
  "schemaVersion": "html-deploy-v1",
  "htmlArtifactKind": "quiz",
  "pageStage": "pre_sales",
  "quizId": "tenor-testosterone-quiz",
  "quizVersion": "v1",
  "quizVariant": "control",
  "quizQuestions": [
    {
      "id": "age",
      "selector": "[data-quiz-question='age']",
      "questionId": "age",
      "questionText": "How old are you?",
      "questionIndex": 1,
      "questionType": "single_select"
    }
  ],
  "quizOptions": [
    {
      "id": "age-50-plus",
      "selector": "[data-quiz-option='age-50-plus']",
      "questionId": "age",
      "optionId": "50_plus",
      "optionText": "50+ Years Old",
      "optionIndex": 1,
      "selectionOrder": 1,
      "submitOnSelect": true
    }
  ]
}
```

## Multi-Select Example

```json
{
  "quizQuestions": [
    {
      "id": "symptoms",
      "selector": "[data-quiz-question='symptoms']",
      "questionId": "symptoms",
      "questionText": "Which symptoms are you noticing?",
      "questionIndex": 2,
      "questionType": "multi_select"
    }
  ],
  "quizOptions": [
    {
      "id": "symptom-energy",
      "selector": "[data-quiz-option='symptom-energy']",
      "questionId": "symptoms",
      "optionId": "low_energy",
      "optionText": "Low energy",
      "optionIndex": 1,
      "selectionOrder": 2
    },
    {
      "id": "symptom-drive",
      "selector": "[data-quiz-option='symptom-drive']",
      "questionId": "symptoms",
      "optionId": "low_drive",
      "optionText": "Low drive",
      "optionIndex": 2,
      "selectionOrder": 3
    }
  ],
  "quizSubmissions": [
    {
      "id": "symptoms-next",
      "selector": "[data-quiz-submit='symptoms']",
      "questionId": "symptoms"
    }
  ]
}
```

## Validator Behavior

The validator clicks options in ascending `selectionOrder`. It does not pick the first visible option as a fallback. Missing answer metadata fails preflight with a direct manifest error.

Required PostHog readback fields:

- `QuizQuestionViewed`: `question_id`, `question_text`
- `QuizOptionPresented`: `question_id`, `question_text`, `option_id`, `option_text`
- `QuizOptionSelected`: `selected_option_ids`, `selected_option_texts`
- `QuizQuestionSubmitted`: `selected_option_ids`, `selected_option_texts`
- `QuizCompleted`: `answers[]` with question ids/text and selected option ids/text

This gives dashboards answer visibility directly in PostHog and keeps new quiz deploys from requiring manual recording review.
