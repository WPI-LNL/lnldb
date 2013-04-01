#import autocomplete_light

#from models import Organization
#from django.contrib.auth.models import User

##autocomplete_light.register(Organization,
    ##search_fields =['^name'],
    ##autocomplete_js_attributes={'placeholder':'Organization Name',},
    ##)
        
#autocomplete_light.register(User,
    #search_fields=['^first_name', 'last_name', 'username'],
    #autocomplete_js_attributes={'placeholder':'Organization Name',},
    #)
        
            
##class UserAutocomplete(autocomplete_light.AutocompleteModelBase):
    ##search_fields = ['^first_name', 'last_name', 'username']

##autocomplete_light.register(User,UserAutocomplete)


#class OrganizationAutocomplete(autocomplete_light.AutocompleteModelBase):
    #search_fields = ['name']

#autocomplete_light.register(Organization,OrganizationAutocomplete)