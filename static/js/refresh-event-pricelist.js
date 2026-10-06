document.addEventListener('DOMContentLoaded', function () {
    const pricelistSelect = document.getElementById('id_pricelist');
    const servicesContainer = document.getElementById('form_data');
    const feesContainer = document.getElementById('div_id_applied_fees');
    const discountsContainer = document.getElementById('div_id_applied_discounts');
    const loadPricelistUrl = document.getElementById('services').dataset.loadPricelistUrl;

    function refreshServices(serviceList) {
        const fields = servicesContainer.querySelectorAll('select[id$="-service"]');
        if (!serviceList) {
            fields.forEach(field => field.innerHTML = '<option value selected>---------</option>');
            return;
        }
        fields.forEach(field => {
            const preserveValue = field.value;
            field.innerHTML = '<option value selected>---------</option>';
            serviceList.forEach(item => {
                const option = document.createElement('option');
                option.value = item.id;
                option.textContent = item.longname;
                if (preserveValue && String(item.id) === preserveValue) {
                    option.selected = true;
                }
                field.appendChild(option);
            })
        })
    }

    function refreshCheckboxes(allowedList, container) {
        const checkboxes = container.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            console.log(allowedList);
            const isAllowed = allowedList.some(item => item.id === parseInt(checkbox.value, 10));
            const listItem = checkbox.closest('div');

            if (!isAllowed)  {
                checkbox.checked = false;
                if (listItem) listItem.style.display = 'none';
            } else {
                if (listItem) listItem.style.display = '';
            }
        });
    }
    function changePricelist(newPricelistId) {
        fetch(`${loadPricelistUrl}?pricelist=${newPricelistId}`)
            .then(response => response.json())
            .then(data => {
                refreshServices(data.services);
                refreshCheckboxes(data.fees, feesContainer);
                refreshCheckboxes(data.discounts, discountsContainer);
            })
            .catch(error => console.error('Error loading new pricelist:', error));
    }

    pricelistSelect.addEventListener('change', function () {
        changePricelist(this.value);
    });

    servicesContainer.addEventListener('formset:row-added', function () {
        changePricelist(pricelistSelect.value);
    });

    if (pricelistSelect.value) {
        changePricelist(pricelistSelect.value);
    }
});
