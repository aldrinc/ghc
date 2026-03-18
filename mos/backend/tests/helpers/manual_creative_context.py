from __future__ import annotations


def manual_creative_context_payload(*, campaign_id: str) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "provider": "manual",
        "angles": {
            "selectedAngleId": "angle-1",
            "angleLibrary": [
                {
                    "angleId": "angle-1",
                    "angleName": "Structured relief path",
                    "description": "Lead with a structured process instead of hype.",
                    "evidence": ["Customers want a safer way to evaluate options."],
                },
                {
                    "angleId": "angle-2",
                    "angleName": "Mechanism before miracle",
                    "description": "Explain the mechanism and avoid exaggerated claims.",
                    "evidence": ["Research-minded buyers distrust miracle framing."],
                },
            ],
        },
        "offer": {
            "ump": "Process clarity before purchase",
            "ums": "Mechanism-first decision support",
            "corePromise": "Understand the offer before you commit",
            "valueStackSummary": "Clear evaluation steps plus practical support",
            "guaranteeType": "standard",
            "pricingRationale": "Price is justified by guided decision support and reusable education.",
            "selectedVariantId": "offer-1",
            "selectedVariantName": "Education-first offer",
            "offerDetailsMarkdown": "## Offer\nA guided, evidence-aware decision path with practical next steps.",
        },
        "copy": {
            "headline": "A clearer way to evaluate the offer",
            "promiseContract": {
                "loopQuestion": "What should I verify before I buy?",
                "specificPromise": "You will leave with a concrete evaluation path.",
                "deliveryTest": "The copy must explain the decision path without unsupported claims.",
                "minimumDelivery": "One clear presell path and one clear sales path.",
            },
            "presellMarkdown": "# Presell\nExplain the evaluation path in plain language.",
            "salesPageMarkdown": "# Sales\nPresent the offer with proof-aware language.",
            "templatePayloads": {
                "pre-sales-listicle": {"hero": {"title": "A clearer evaluation path"}},
                "sales-pdp": {"hero": {"title": "Education-first offer"}},
            },
        },
        "copyContext": {
            "audienceProductMarkdown": "Audience wants a structured way to evaluate outcomes and risk.",
            "brandVoiceMarkdown": "Calm, direct, practical, non-hyped.",
            "complianceMarkdown": "Avoid medical promises and unsupported clinical claims.",
            "mentalModelsMarkdown": "Decision support, mechanism, clarity before commitment.",
            "awarenessAngleMatrixMarkdown": "Angle one: structured relief path. Angle two: mechanism before miracle.",
        },
        "experimentSpecs": [
            {
                "id": "exp-manual-1",
                "name": "Structured relief path",
                "hypothesis": "A structured evaluation angle will improve quality traffic.",
                "metricIds": ["ctr", "cvr"],
                "variants": [
                    {
                        "id": "var_control_generic",
                        "name": "Generic control",
                        "description": "Control focused on general relief framing.",
                        "channels": ["facebook"],
                        "guardrails": ["Avoid unsupported claims."],
                    },
                    {
                        "id": "var_angle",
                        "name": "Structured angle",
                        "description": "Angle focused on a clearer evaluation path.",
                        "channels": ["facebook"],
                        "guardrails": ["Avoid unsupported claims."],
                    },
                ],
            }
        ],
    }
