export interface CompanySwipeAsset {
  id: string;
  org_id: string;
  title?: string;
  body?: string;
  platforms?: string;
}

export interface ClientSwipeAsset {
  id: string;
  org_id: string;
  client_id: string;
  company_swipe_id?: string;
  tags: string[];
}
