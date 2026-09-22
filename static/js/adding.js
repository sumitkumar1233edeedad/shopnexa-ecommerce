querySelectorAll(".product-detail-quantity-control").forEach(control => {

    const minus = control.querySelector(".product-detail-quantity-minus");
    const plus = control.querySelector(".product-detail-quantity-plus");
    const input = control.querySelector(".product-detail-quantity-input");

    minus.addEventListener("click", () => {
        let quantity = parseInt(input.value) || 1;

        if (quantity > 1) {
            input.value = quantity - 1;
        }
    });

    plus.addEventListener("click", () => {
        let quantity = parseInt(input.value) || 1;
        let max = parseInt(input.max);

        if (!max || quantity < max) {
            input.value = quantity + 1;
        }
    });

    input.addEventListener("change", () => {
        let quantity = parseInt(input.value) || 1;
        let max = parseInt(input.max);

        if (quantity < 1) {
            quantity = 1;
        }

        if (max && quantity > max) {
            quantity = max;
        }

        input.value = quantity;
    });

});
 