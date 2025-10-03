#!/usr/bin/env python3
"""
Clear Azure AI Search index completely
"""
import os
import sys
sys.path.append('../../shared')

from evidentfit_shared.search_client import ensure_index

def clear_index():
    """Clear all documents from the Azure AI Search index"""
    try:
        # Get the index name
        index_name = os.getenv("SEARCH_INDEX", "evidentfit-index")
        print(f"Clearing index: {index_name}")
        
        # Delete all documents by searching for all and deleting
        from evidentfit_shared.search_client import search_docs
        
        # Search for all documents
        response = search_docs(query="*", top=10000)
        
        if response and 'value' in response:
            docs = response['value']
            print(f"Found {len(docs)} documents to delete")
            
            if docs:
                # Delete documents in batches
                from evidentfit_shared.search_client import delete_docs
                
                batch_size = 50
                for i in range(0, len(docs), batch_size):
                    batch = docs[i:i+batch_size]
                    doc_ids = [doc['id'] for doc in batch]
                    
                    try:
                        delete_docs(doc_ids)
                        print(f"Deleted batch {i//batch_size + 1}: {len(doc_ids)} documents")
                    except Exception as e:
                        print(f"Error deleting batch {i//batch_size + 1}: {e}")
            else:
                print("No documents found to delete")
        else:
            print("No documents found in index")
            
        print("Index clearing complete")
        
    except Exception as e:
        print(f"Error clearing index: {e}")
        return False
        
    return True

if __name__ == "__main__":
    success = clear_index()
    sys.exit(0 if success else 1)
