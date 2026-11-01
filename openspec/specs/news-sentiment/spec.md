# news-sentiment Specification

## Purpose

A news-sentiment signal for the AI paper-trading stack: a sentiment-scoring service
contract (FinBERT served via ONNX Runtime, reached behind a `SentimentScorer`
Protocol), a news source (Alpaca News / Benzinga), a trailing-window recency-weighted
tone aggregation cached per `(ticker, date)`, and a graceful-degradation contract so
the feature is strictly additive and never fails a rebalance.

## Requirements

### Requirement: Sentiment scoring behind a provider contract

The system SHALL obtain per-headline sentiment through a sentiment-scorer **Protocol**
with a real implementation and an injectable stub, mirroring how the system isolates
market data, the broker, and the recommender agent. The real implementation SHALL be a
thin client of a **separate sentiment-scoring service** that classifies financial text
into positive / neutral / negative tone (FinBERT lineage, served via ONNX Runtime). The
scorer contract SHALL accept one or more text items and return, per item, the tone
class probabilities (or a tone leaning derived from them). The backend SHALL NOT load
the model in-process; scoring SHALL be an out-of-process call so the backend stays lean.

The scoring service SHALL expose a health endpoint and SHALL warm-load its model at
startup so that it only reports healthy once it can score. The service URL SHALL be
configurable, and when it is **unset the sentiment feature SHALL be disabled** (treated
as universally unavailable) rather than erroring.

#### Scenario: Scorer returns tone for supplied text

- **WHEN** the real scorer is configured and asked to score one or more news texts
- **THEN** it SHALL call the sentiment service and return a per-text tone result
  (positive / neutral / negative leaning)

#### Scenario: Stub scorer used offline and in tests

- **WHEN** the system runs with the stub scorer injected
- **THEN** sentiment SHALL be produced without any network call to the service

#### Scenario: Unconfigured service disables the feature

- **WHEN** the sentiment service URL is unset
- **THEN** the system SHALL treat sentiment as universally unavailable rather than
  raising, so dependent flows degrade gracefully

### Requirement: News retrieval for sentiment

The system SHALL retrieve recent news items for a given ticker over a trailing window
from a news source (the Alpaca News API / Benzinga), reusing the existing Alpaca
credentials. Retrieval SHALL be behind a provider seam with an injectable stub for
tests and offline runs. The window length SHALL be configurable with a sensible default
of about three days. When the source returns no items for a ticker in the window, the
system SHALL treat that ticker as having no usable sentiment rather than erroring.

#### Scenario: Fetch recent news for a ticker

- **WHEN** news is requested for a ticker over the trailing window
- **THEN** the system SHALL return the news items the source has for that ticker in the
  window, newest first

#### Scenario: No news in the window

- **WHEN** the news source returns no items for a ticker in the window
- **THEN** the system SHALL report no usable sentiment for that ticker rather than
  raising

### Requirement: Trailing-window aggregated tone signal

The system SHALL compute a per-ticker aggregate tone signal from the scored news in the
trailing window as a **recency-weighted mean of each item's (positive − negative)
probability**, so more recent items carry more weight, together with the **count of
articles** the signal was derived from. The aggregate SHALL be classified into a
human-readable leaning (positive / neutral / negative) for the rebalance prompt. The
aggregation SHALL be deterministic given the same inputs. Computed signals SHALL be
cached keyed by `(ticker, date)` so repeated reads within a day reuse the result rather
than re-scoring.

#### Scenario: Aggregate weights recent news more

- **WHEN** a ticker has several scored news items of differing dates in the window
- **THEN** the aggregate tone SHALL be the recency-weighted mean of their
  (positive − negative) scores, carried with the article count

#### Scenario: Deterministic and cached per ticker-day

- **WHEN** the aggregate for a `(ticker, date)` is requested more than once in the same
  day with the same underlying news
- **THEN** the system SHALL return the same signal and SHALL reuse the cached value
  rather than re-scoring

### Requirement: Graceful degradation of the sentiment signal

The sentiment signal SHALL be strictly additive and non-blocking. When the sentiment
service is unconfigured, unreachable, errors, or returns no usable result — or when a
ticker has no news in the window — the system SHALL yield an explicit **"sentiment
unavailable"** result for the affected tickers rather than raising, so a consumer
(the rebalance flow) can mark those tickers unavailable and proceed unchanged. The
sentiment path SHALL never fail a rebalance.

#### Scenario: Service error degrades, does not raise

- **WHEN** the sentiment service is unreachable or returns an error while scoring a
  ticker's news
- **THEN** the system SHALL yield "sentiment unavailable" for that ticker rather than
  propagating an error

#### Scenario: Partial availability

- **WHEN** some requested tickers have usable sentiment and others have none
- **THEN** the system SHALL return available signals for the former and
  "sentiment unavailable" for the latter, without failing the batch
